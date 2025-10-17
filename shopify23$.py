from flask import Flask, request, jsonify
import requests
import uuid
import os

app = Flask(__name__)

# Configuration for Shopify API endpoints
SHOPIFY_SESSION_URL = os.getenv('SHOPIFY_SESSION_URL', 'https://checkout.pci.shopifyinc.com/sessions')
SHOPIFY_CHECKOUT_URL = os.getenv('SHOPIFY_CHECKOUT_URL', 'https://www.vanguardmil.com/checkouts/unstable/graphql')

# Headers for Shopify session request
session_headers = {
    'accept': 'application/json',
    'accept-language': 'en-US,en;q=0.9',
    'content-type': 'application/json',
    'origin': 'https://checkout.pci.shopifyinc.com',
    'priority': 'u=1, i',
    'referer': 'https://checkout.pci.shopifyinc.com/build/102f5ed/number-ltr.html',
    'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-storage-access': 'active',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
}

# Headers for checkout submission and polling
checkout_headers = {
    'accept': 'application/json',
    'accept-language': 'en-US',
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
    'x-checkout-one-session-token': os.getenv('CHECKOUT_SESSION_TOKEN', 'AAEBQjASMCKIMMo0cQPwMGutxb4UE5o3USInziN-TxyMi3uSCWP2Vo_1AJXLpkdrvl7sjT_xQUBawyQNzcYt3p6APfGrRXhDioEuPZhTfEq3vuHElP8ajaKdkI-RstIS1DwqbcCRYHbgUyGb39lmYOgVoOmwcOUXofzCG3xAWLA6mVNj6vPYFvLFZ5lUI17-BOqPi4-uU_EbSdnkXNNON4_3GQ'),
    'x-checkout-web-build-id': '1425498c9f082684649666eafda564f07561d25c',
    'x-checkout-web-deploy-stage': 'production',
    'x-checkout-web-server-handling': 'fast',
    'x-checkout-web-server-rendering': 'yes',
    'x-checkout-web-source-id': 'hWN1DD0iR9Rfnqmheh7rVKMb',
}

# Cookies for checkout requests
cookies = {
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

@app.route('/gateway=sh23$/cc=', methods=['GET'])
def process_credit_card_payment():
    try:
        # Extract query parameters
        card_number = request.args.get('card_number')
        month = request.args.get('month', type=int)
        year = request.args.get('year', type=int)
        verification_value = request.args.get('verification_value')
        name = request.args.get('name')
        payment_session_scope = request.args.get('payment_session_scope', 'vanguardmil.com')
        address1 = request.args.get('address1', 'New York')
        address2 = request.args.get('address2', 'New York')
        city = request.args.get('city', 'New York')
        country_code = request.args.get('countryCode', 'US')
        postal_code = request.args.get('postalCode', '10200')
        first_name = request.args.get('firstName', 'Dark')
        last_name = request.args.get('lastName', 'Boy')
        zone_code = request.args.get('zoneCode', 'NY')
        phone = request.args.get('phone', '9685698569')
        email = request.args.get('email', 'kjbksefb@gmail.com')
        buyer_country_code = request.args.get('buyerCountryCode', 'IN')
        phone_country_code = request.args.get('phoneCountryCode', 'IN')
        quantity = request.args.get('quantity', 1, type=int)
        amount = request.args.get('amount', '3.50')
        total_amount = request.args.get('total_amount', '23.3')
        request_url = request.args.get('requestUrl', 'https://www.vanguardmil.com/checkouts/cn/hWN1DD0iR9Rfnqmheh7rVKMb?cart_link_id=LT5dG7f5')

        if not all([card_number, month, year, verification_value, name]):
            return jsonify({'error': 'Missing required credit card fields'}), 400

        # Step 1: Create payment session
        session_data = {
            'credit_card': {
                'number': card_number,
                'month': month,
                'year': year,
                'verification_value': verification_value,
                'start_month': None,
                'start_year': None,
                'issue_number': '',
                'name': name,
            },
            'payment_session_scope': payment_session_scope,
        }

        session_response = requests.post(SHOPIFY_SESSION_URL, headers=session_headers, json=session_data)
        if session_response.status_code != 200:
            return jsonify({'error': 'Failed to create payment session', 'details': session_response.text}), 500

        session_result = session_response.json()
        payment_method_identifier = session_result.get('id')
        if not payment_method_identifier:
            return jsonify({'error': 'No payment method identifier received'}), 500

        # Step 2: Submit checkout for completion
        checkout_data = {
            'query': '''mutation SubmitForCompletion($input: NegotiationInput!, $attemptToken: String!, $metafields: [MetafieldInput!], $postPurchaseInquiryResult: PostPurchaseInquiryResultCode, $analytics: AnalyticsInput) {
                submitForCompletion(input: $input, attemptToken: $attemptToken, metafields: $metafields, postPurchaseInquiryResult: $postPurchaseInquiryResult, analytics: $analytics) {
                    ... on SubmitSuccess { receipt { ...ReceiptDetails } }
                    ... on SubmitAlreadyAccepted { receipt { ...ReceiptDetails } }
                    ... on SubmitFailed { reason }
                    ... on SubmitRejected { errors { code localizedMessage } }
                    ... on Throttled { pollAfter pollUrl queueToken }
                    ... on CheckpointDenied { redirectUrl }
                    ... on TooManyAttempts { redirectUrl }
                    ... on SubmittedForCompletion { receipt { ...ReceiptDetails } }
                }
            }
            fragment ReceiptDetails on Receipt {
                ... on ProcessedReceipt {
                    id
                    token
                    redirectUrl
                    confirmationPage { url shouldRedirect }
                    orderStatusPageUrl
                    paymentDetails { paymentCardBrand creditCardLastFourDigits paymentAmount { amount currencyCode } }
                }
                ... on ProcessingReceipt { id pollDelay }
                ... on WaitingReceipt { id pollDelay }
                ... on ActionRequiredReceipt { id action { ... on CompletePaymentChallenge { offsiteRedirect url } } }
                ... on FailedReceipt { id processingError { code messageUntranslated } }
            }''',
            'variables': {
                'input': {
                    'sessionInput': {
                        'sessionToken': checkout_headers['x-checkout-one-session-token'],
                    },
                    'queueToken': f'A0BuViNF5uWuojW64-m4dv3G7CbZ8SY9ekvTyHZLbEUgccVE8Hqv2x3N6_xX_gez1xCHNoNlHmMlGZz6Z0KiJvSEZb23F7EG3xsHLyBc-1x2A_My',
                    'discounts': {
                        'lines': [],
                        'acceptUnexpectedDiscounts': True,
                    },
                    'delivery': {
                        'deliveryLines': [{
                            'destination': {
                                'streetAddress': {
                                    'address1': address1,
                                    'address2': address2,
                                    'city': city,
                                    'countryCode': country_code,
                                    'postalCode': postal_code,
                                    'firstName': first_name,
                                    'lastName': last_name,
                                    'zoneCode': zone_code,
                                    'phone': phone,
                                    'oneTimeUse': False,
                                },
                            },
                            'selectedDeliveryStrategy': {
                                'deliveryStrategyByHandle': {
                                    'handle': '84b346bc8248a38a15eb63cb0acbfaf5-637d968cc49b21b877b3f8441beae1e1',
                                    'customDeliveryRate': False,
                                },
                                'options': {
                                    'phone': phone,
                                },
                            },
                            'targetMerchandiseLines': {
                                'lines': [{
                                    'stableId': str(uuid.uuid4()),
                                }],
                            },
                            'deliveryMethodTypes': ['SHIPPING'],
                            'expectedTotalPrice': {
                                'value': {
                                    'amount': '19.80',
                                    'currencyCode': 'USD',
                                },
                            },
                            'destinationChanged': False,
                        }],
                        'useProgressiveRates': False,
                        'supportsSplitShipping': True,
                    },
                    'merchandise': {
                        'merchandiseLines': [{
                            'stableId': str(uuid.uuid4()),
                            'merchandise': {
                                'productVariantReference': {
                                    'id': 'gid://shopify/ProductVariantMerchandise/12379973845046',
                                    'variantId': 'gid://shopify/ProductVariant/12379973845046',
                                    'properties': [],
                                    'sellingPlanId': None,
                                    'sellingPlanDigest': None,
                                },
                            },
                            'quantity': {
                                'items': {
                                    'value': quantity,
                                },
                            },
                            'expectedTotalPrice': {
                                'value': {
                                    'amount': amount,
                                    'currencyCode': 'USD',
                                },
                            },
                            'lineComponentsSource': None,
                            'lineComponents': [],
                        }],
                    },
                    'payment': {
                        'totalAmount': {
                            'any': True,
                        },
                        'paymentLines': [{
                            'paymentMethod': {
                                'directPaymentMethod': {
                                    'paymentMethodIdentifier': payment_method_identifier,
                                    'sessionId': session_result.get('session_id', 'west-bd6eca1c027ee66479ac2284d5e70eaa'),
                                    'billingAddress': {
                                        'streetAddress': {
                                            'address1': address1,
                                            'address2': address2,
                                            'city': city,
                                            'countryCode': country_code,
                                            'postalCode': postal_code,
                                            'firstName': first_name,
                                            'lastName': last_name,
                                            'zoneCode': zone_code,
                                            'phone': phone,
                                        },
                                    },
                                    'cardSource': None,
                                },
                            },
                            'amount': {
                                'value': {
                                    'amount': total_amount,
                                    'currencyCode': 'USD',
                                },
                            },
                        }],
                        'billingAddress': {
                            'streetAddress': {
                                'address1': address1,
                                'address2': address2,
                                'city': city,
                                'countryCode': country_code,
                                'postalCode': postal_code,
                                'firstName': first_name,
                                'lastName': last_name,
                                'zoneCode': zone_code,
                                'phone': phone,
                            },
                        },
                    },
                    'buyerIdentity': {
                        'customer': {
                            'presentmentCurrency': 'USD',
                            'countryCode': buyer_country_code,
                        },
                        'email': email,
                        'emailChanged': False,
                        'phoneCountryCode': phone_country_code,
                        'marketingConsent': [],
                        'shopPayOptInPhone': {
                            'number': phone,
                            'countryCode': phone_country_code,
                        },
                        'rememberMe': False,
                    },
                    'taxes': {
                        'proposedTotalAmount': {
                            'value': {
                                'amount': '0',
                                'currencyCode': 'USD',
                            },
                        },
                        'proposedExemptions': [],
                    },
                    'note': {
                        'message': None,
                        'customAttributes': [],
                    },
                    'localizationExtension': {
                        'fields': [],
                    },
                    'optionalDuties': {
                        'buyerRefusesDuties': False,
                    },
                    'cartMetafields': [],
                },
                'attemptToken': f'hWN1DD0iR9Rfnqmheh7rVKMb-{str(uuid.uuid4())[:8]}',
                'metafields': [{
                    'key': 'views',
                    'namespace': 'checkoutblocks',
                    'value': '{"blocks":["68701fd10734c931da8bd522","669808171ccb91cf0ee2a23c"]}',
                    'valueType': 'JSON_STRING',
                    'appId': 'gid://shopify/App/4748640257',
                }],
                'analytics': {
                    'requestUrl': request_url,
                    'pageId': str(uuid.uuid4()),
                },
            },
            'operationName': 'SubmitForCompletion',
        }

        checkout_response = requests.post(
            SHOPIFY_CHECKOUT_URL,
            params={'operationName': 'SubmitForCompletion'},
            cookies=cookies,
            headers=checkout_headers,
            json=checkout_data,
        )

        if checkout_response.status_code != 200:
            return jsonify({'error': 'Failed to submit checkout', 'details': checkout_response.text}), 500

        checkout_result = checkout_response.json()
        receipt_id = checkout_result.get('data', {}).get('submitForCompletion', {}).get('receipt', {}).get('id')

        if not receipt_id:
            return jsonify({'error': 'No receipt ID received', 'details': checkout_result}), 500

        # Step 3: Poll for receipt status
        poll_data = {
            'query': '''query PollForReceipt($receiptId: ID!, $sessionToken: String!) {
                receipt(receiptId: $receiptId, sessionInput: { sessionToken: $sessionToken }) {
                    ...ReceiptDetails
                }
            }
            fragment ReceiptDetails on Receipt {
                ... on ProcessedReceipt {
                    id
                    token
                    redirectUrl
                    confirmationPage { url shouldRedirect }
                    orderStatusPageUrl
                    paymentDetails { paymentCardBrand creditCardLastFourDigits paymentAmount { amount currencyCode } }
                }
                ... on ProcessingReceipt { id pollDelay }
                ... on WaitingReceipt { id pollDelay }
                ... on ActionRequiredReceipt { id action { ... on CompletePaymentChallenge { offsiteRedirect url } } }
                ... on FailedReceipt { id processingError { code messageUntranslated } }
            }''',
            'variables': {
                'receiptId': receipt_id,
                'sessionToken': checkout_headers['x-checkout-one-session-token'],
            },
            'operationName': 'PollForReceipt',
        }

        poll_response = requests.post(
            SHOPIFY_CHECKOUT_URL,
            params={'operationName': 'PollForReceipt'},
            cookies=cookies,
            headers=checkout_headers,
            json=poll_data,
        )

        if poll_response.status_code != 200:
            return jsonify({'error': 'Failed to poll receipt', 'details': poll_response.text}), 500

        return jsonify(poll_response.json()), 200

    except Exception as e:
        return jsonify({'error': 'Internal server error', 'details': str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
