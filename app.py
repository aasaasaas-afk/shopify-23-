from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

def check_paypal_card(cc_details):
    """Check PayPal status using the new API endpoint"""
    if not len(cc_details.split('|')) == 4:
        return {
            "response": "Invalid format. Use CC|MM|YYYY|CVV",
            "status": "DECLINED",
            "gateway": "Paypal [0.1$]"
        }

    url = f"http://ravenxchecker.site/check/ppa.php?lista={cc_details}"

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()  # Raise exception for HTTP errors
        
        # Parse the JSON response
        data = response.json()
        
        # Determine status based on API's "status" field
        if data['status'] == "LIVE":
            # For LIVE status, determine response based on response_code
            if data['response_code'] == "SUCCESS":
                return {
                    "gateway": "Paypal [0.1$]",
                    "response": "CARD ADDED",
                    "status": "approved"
                }
            elif data['response_code'] == "ACCOUNT_RESTRICTED":
                return {
                    "gateway": "Paypal [0.1$]",
                    "response": "EXISTING_ACCOUNT_RESTRICTED",
                    "status": "approved"
                }
            elif data['response_code'] == "3DS_REQUIRED":
                return {
                    "gateway": "Paypal [0.1$]",
                    "response": "3DS VERIFICATION REQUIRED",
                    "status": "approved"
                }
            elif data['response_code'] == "CARD_GENERIC_ERROR":
                return {
                    "gateway": "Paypal [0.1$]",
                    "response": "ISSUER_DECLINE",
                    "status": "declined"
                }
            else:
                return {
                    "gateway": "Paypal [0.1$]",
                    "response": data['response_code'],
                    "status": "approved"
                }
                
        elif data['status'] == "DEAD":
            # For DEAD status, check for special response codes
            if data['response_code'] == "3DS_REQUIRED":
                return {
                    "gateway": "Paypal [0.1$]",
                    "response": "CARD DECLINED",
                    "status": "declined"
                }
            elif data['response_code'] == "CARD_GENERIC_ERROR":
                return {
                    "gateway": "Paypal [0.1$]",
                    "response": "CARD DECLINED",
                    "status": "declined"
                }
            elif data['response_code'] == "UNKNOWN_ERROR":
                return {
                    "gateway": "Paypal [0.1$]",
                    "response": "CARD DECLINED",
                    "status": "declined"
                }                
            else:
                return {
                    "gateway": "Paypal [0.1$]",
                    "response": data['response_code'],
                    "status": "declined"
                }
                
        else:
            # Handle unexpected status values
            return {
                "gateway": "Paypal [0.1$]",
                "response": f"UNKNOWN_STATUS: {data['status']}",
                "status": "error"
            }
            
    except requests.exceptions.RequestException as e:
        return {
            "response": f"API_REQUEST_ERROR: {str(e)}",
            "status": "ERROR",
            "gateway": "Paypal [0.1$]"
        }
    except ValueError:  # Invalid JSON
        return {
            "response": "INVALID_API_RESPONSE",
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
