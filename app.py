import requests
import json
import logging
import re
import time
from fastapi import FastAPI, Query, HTTPException
import uvicorn
from typing import Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Initialize FastAPI App
app = FastAPI(
    title="PayPal Payment Gateway",
    description="Process PayPal payments with card details"
)

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
    "INSUFFICIENT_FUNDS",
    "CARD_DECLINED",
    "PROCESSING_ERROR",
    "SHIPPING_ADDRESS_MISSING"
}

def extract_csrf_token(html_content: str) -> str:
    """Extract CSRF token from HTML content with multiple patterns."""
    patterns = [
        r'"csrfToken":"([^"]+)"',
        r'csrfToken["\']?\s*:\s*["\']([^"\']+)["\']',
        r'name=["\']csrf["\']\s+value=["\']([^"\']+)["\']',
        r'data-csrf=["\']([^"\']+)["\']',
        r'"token":"([^"]+)"',
        r'name="_token"\s+value="([^"]+)"',
        r'window\.csrfToken\s*=\s*["\']([^"\']+)["\']'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, html_content)
        if match:
            logging.info(f"CSRF token found using pattern: {pattern}")
            return match.group(1)
    
    logging.warning(f"CSRF token not found. Page content snippet: {html_content[:500]}...")
    return None

def create_session() -> requests.Session:
    """Create a requests session with proper headers."""
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'Sec-Ch-Ua': '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1'
    })
    return session

def process_paypal_payment(card_details_string: str, amount: str = "1.00") -> Dict[str, Any]:
    """
    Processes the PayPal payment using the provided card details string.
    The string should be in the format: 'card_number|mm|yy|cvv'
    Returns a dictionary with processing results.
    """
    start_time = time.time()
    
    # --- 1. Parse and Validate Card Details ---
    parts = card_details_string.split('|')
    if len(parts) != 4:
        return {
            'code': 'VALIDATION_ERROR',
            'message': 'Invalid card details format',
            'status': 'declined'
        }

    card_number, month, year, cvv = [p.strip() for p in parts]

    # Validate card number
    if not re.match(r'^\d{13,19}$', card_number):
        return {
            'code': 'VALIDATION_ERROR',
            'message': 'Invalid card number',
            'status': 'declined'
        }

    # Validate month
    if not month.isdigit() or len(month) != 2 or not (1 <= int(month) <= 12):
        return {
            'code': 'INVALID_MONTH',
            'message': 'Invalid expiration month',
            'status': 'declined'
        }
    
    # Validate year
    if not year.isdigit():
        return {
            'code': 'VALIDATION_ERROR',
            'message': 'Invalid expiration year',
            'status': 'declined'
        }
    
    if len(year) == 2: 
        year = '20' + year
    elif len(year) != 4: 
        return {
            'code': 'VALIDATION_ERROR',
            'message': 'Invalid year format',
            'status': 'declined'
        }
    
    # Check if card is expired
    current_year = time.strftime('%Y')
    current_month = time.strftime('%m')
    if year < current_year or (year == current_year and month < current_month):
        return {
            'code': 'EXPIRED_CARD',
            'message': 'Card has expired',
            'status': 'declined'
        }
    
    # Validate CVV
    if not cvv.isdigit() or not (3 <= len(cvv) <= 4):
        return {
            'code': 'VALIDATION_ERROR',
            'message': 'Invalid CVV',
            'status': 'declined'
        }

    expiry_date = f"{month}/{year}"
    card_type = 'VISA' if card_number.startswith('4') else ('MASTER_CARD' if card_number.startswith('5') else ('AMEX' if card_number.startswith('3') else 'UNKNOWN'))
    currency_conversion_type = 'VENDOR' if card_type == 'AMEX' else 'PAYPAL'
    
    card_details = {
        'cardNumber': card_number,
        'type': card_type,
        'expirationDate': expiry_date,
        'securityCode': cvv,
        'postalCode': '10010'
    }

    # Address details
    address_details = {
        'givenName': 'John',
        'familyName': 'Doe',
        'line1': '123 Main St',
        'line2': 'Apt 4B',
        'city': 'New York',
        'state': 'NY',
        'postalCode': '10010',
        'country': 'US'
    }

    # --- 2. Execute PayPal Request Sequence ---
    session = create_session()
    token = None
    
    try:
        # Step 1: Get CSRF token
        csrf_token = None
        for attempt in range(3):
            try:
                response = session.get(
                    'https://www.paypal.com/ncp/payment/R2FGT68WSSRLW',
                    timeout=15
                )
                response.raise_for_status()
                
                csrf_token = extract_csrf_token(response.text)
                if csrf_token:
                    logging.info(f"CSRF token obtained on attempt {attempt + 1}")
                    break
                else:
                    logging.warning(f"CSRF token not found on attempt {attempt + 1}")
                    if attempt < 2:
                        time.sleep(2)
            except Exception as e:
                logging.error(f"Error getting CSRF token on attempt {attempt + 1}: {e}")
                if attempt < 2:
                    time.sleep(2)
        
        if not csrf_token:
            return {
                'code': 'TOKEN_EXTRACTION_ERROR',
                'message': 'Failed to obtain CSRF token',
                'status': 'declined'
            }

        # Step 2: Create order with retry for CSRF mismatch
        order_created = False
        for attempt in range(3):
            headers = {
                'Accept': '*/*',
                'Content-Type': 'application/json',
                'Origin': 'https://www.paypal.com',
                'Referer': 'https://www.paypal.com/ncp/payment/R2FGT68WSSRLW',
                'X-CSRF-Token': csrf_token,
                'X-Requested-With': 'XMLHttpRequest'
            }
            
            json_data = {
                'link_id': 'R2FGT68WSSRLW',
                'merchant_id': '32BACX6X7PYMG',
                'quantity': '1',
                'amount': amount,
                'currency': 'USD',
                'currencySymbol': '$',
                'funding_source': 'CARD',
                'button_type': 'VARIABLE_PRICE',
                'csrfRetryEnabled': True
            }
            
            try:
                response = session.post(
                    'https://www.paypal.com/ncp/api/create-order',
                    headers=headers,
                    json=json_data,
                    timeout=10
                )
                
                # Check for CSRF mismatch
                if response.status_code == 403:
                    try:
                        error_data = response.json()
                        if error_data.get('message') == 'CSRF_MISMATCH_RETRY' and 'csrfToken' in error_data:
                            csrf_token = error_data['csrfToken']
                            logging.info(f"Got new CSRF token for retry: {csrf_token[:20]}...")
                            continue
                    except:
                        pass
                
                response.raise_for_status()
                response_data = response.json()
                
                if 'context_id' in response_data:
                    token = response_data['context_id']
                    logging.info(f"Payment token obtained: {token}")
                    order_created = True
                    break
                else:
                    logging.error(f"No context_id in response: {response_data}")
                    
            except requests.exceptions.RequestException as e:
                logging.error(f"Error creating order on attempt {attempt + 1}: {e}")
                if attempt < 2:
                    time.sleep(2)
        
        if not order_created or not token:
            return {
                'code': 'TOKEN_EXTRACTION_ERROR',
                'message': 'Failed to create order after retries',
                'status': 'declined'
            }

        # Step 3: Submit card details
        headers = {
            'Accept': '*/*',
            'Content-Type': 'application/json',
            'Origin': 'https://www.paypal.com',
            'PayPal-Client-Context': token,
            'PayPal-Client-Metadata-Id': token,
            'Referer': f'https://www.paypal.com/smart/card-fields?token={token}',
            'X-App-Name': 'standardcardfields',
            'X-Country': 'US'
        }

        graphql_query = """
        mutation payWithCard(
            $token: String!, 
            $card: CardInput, 
            $billingAddress: AddressInput, 
            $shippingAddress: AddressInput,
            $currencyConversionType: CheckoutCurrencyConversionType,
            $phoneNumber: String,
            $email: String,
            $firstName: String,
            $lastName: String
        ) {
            approveGuestPaymentWithCreditCard(
                token: $token
                card: $card
                billingAddress: $billingAddress
                shippingAddress: $shippingAddress
                currencyConversionType: $currencyConversionType
                phoneNumber: $phoneNumber
                email: $email
                firstName: $firstName
                lastName: $lastName
            ) {
                cart {
                    intent
                    cartId
                }
                paymentContingencies {
                    threeDomainSecure {
                        status
                    }
                }
            }
        }
        """
        
        json_data = {
            'query': graphql_query.strip(),
            'variables': {
                'token': token,
                'card': card_details,
                'billingAddress': address_details,
                'shippingAddress': address_details,
                'currencyConversionType': currency_conversion_type,
                'phoneNumber': '4073320637',
                'email': 'rocky2@gmail.com',
                'firstName': 'John',
                'lastName': 'Doe'
            }
        }
        
        response = session.post(
            'https://www.paypal.com/graphql',
            cookies=session.cookies,
            headers=headers,
            json=json_data,
            timeout=20
        )
        response.raise_for_status()
        response_data = response.json()
        
        # Parse response
        if 'errors' in response_data:
            error = response_data['errors'][0]
            error_code = error.get('extensions', {}).get('code', 'UNKNOWN_ERROR')
            error_message = error.get('message', 'Unknown error')
            
            logging.error(f"PayPal error: {error_code} - {error_message}")
            
            # Map PayPal error codes to our standard format
            if error_code == 'SHIPPING_ADDRESS_MISSING':
                mapped_code = 'SHIPPING_ADDRESS_MISSING'
            elif error_code in DECLINED_CODES:
                mapped_code = error_code
            elif error_code in APPROVED_CODES:
                mapped_code = error_code
            else:
                mapped_code = 'UNKNOWN_ERROR'
            
            if mapped_code in APPROVED_CODES:
                return {
                    'code': mapped_code,
                    'message': 'Payment approved',
                    'status': 'approved'
                }
            else:
                return {
                    'code': mapped_code,
                    'message': 'Payment declined',
                    'status': 'declined'
                }
        
        # Check for successful response
        if 'data' in response_data and response_data['data'].get('approveGuestPaymentWithCreditCard'):
            return {
                'code': 'TRANSACTION_SUCCESSFUL',
                'message': 'Payment processed successfully',
                'status': 'charged'
            }
        
        return {
            'code': 'UNKNOWN_ERROR',
            'message': 'Unexpected response from PayPal',
            'status': 'declined'
        }
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Network error: {e}")
        return {
            'code': 'NETWORK_ERROR',
            'message': 'Network error occurred',
            'status': 'declined'
        }
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        return {
            'code': 'INTERNAL_ERROR',
            'message': 'Internal server error',
            'status': 'declined'
        }
    finally:
        end_time = time.time()
        processing_time = f"{end_time - start_time:.2f}s"
        logging.info(f"Processing completed in {processing_time}")

@app.get('/pp')
async def payment_gateway(
    cc: str = Query(..., description="Card details in format: card_number|mm|yy|cvv"),
    amount: str = Query("0.01", description="Payment amount")
):
    """
    Main endpoint to process a payment.
    URL Format: /pp?cc=card_number|mm|yy|cvv&amount=0.01
    """
    last_four = cc.split('|')[0][-4:] if '|' in cc and len(cc.split('|')[0]) >= 4 else '****'
    logging.info(f"Received payment request for card ending in {last_four}, amount: {amount}")
    
    result = process_paypal_payment(cc, amount)
    
    logging.info(f"Transaction result: {result}")
    return result

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=5000)
