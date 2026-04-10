from flask import Flask, request, jsonify
import requests
import re
import time

app = Flask(__name__)

@app.route('/ping')
def ping():
    return jsonify({'status': 'ok'})

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = 'https://halloekes.github.io'
    response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

def get_session():
    session = requests.Session()
    response = session.get('https://www.dresden.de/apps_ext/AbfallApp/wastebins')
    html = response.text
    match = re.search(r'wastebins(;jsessionid=[A-F0-9]+)?\?(\d+(?:-\d+)?)\.2-searchForm-street', html)
    if match:
        jsessionid = match.group(1) if match.group(1) else ''
        token = match.group(2)
        return session, jsessionid, token
    else:
        raise ValueError("Could not extract session info")

def update_token(response_text):
    match = re.search(r'wastebins(?:;jsessionid=[A-F0-9]+)?\?(\d+(?:-\d+)?)?\.', response_text)
    if match:
        return match.group(1)
    return None

@app.route('/streets')
def streets():
    q = request.args.get('q')
    if not q:
        return jsonify({'error': 'Missing query parameter q'}), 400
    try:
        session, jsessionid, token = get_session()
        url = f'https://www.dresden.de/apps_ext/AbfallApp/wastebins{jsessionid}?{token}.2-searchForm-street&q={q}&_={int(time.time()*1000)}'
        headers = {
            'Wicket-Ajax': 'true',
            'Wicket-Ajax-BaseURL': f'wastebins{jsessionid}?{token}',
            'X-Requested-With': 'XMLHttpRequest'
        }
        response = session.get(url, headers=headers)
        matches = re.findall(r'textvalue="([^"]+)"', response.text)
        return jsonify(matches)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/housenumbers')
def housenumbers():
    street = request.args.get('street')
    if not street:
        return jsonify({'error': 'Missing query parameter street'}), 400
    try:
        session, jsessionid, token = get_session()
        headers = {
            'Wicket-Ajax': 'true',
            'Wicket-Ajax-BaseURL': f'wastebins{jsessionid}?{token}',
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        # Erster POST
        url1 = f'https://www.dresden.de/apps_ext/AbfallApp/wastebins{jsessionid}?{token}.0-searchForm-street'
        data1 = f'street={requests.utils.quote(street)}'
        response1 = session.post(url1, headers=headers, data=data1)
        new_token = update_token(response1.text)
        if new_token:
            token = new_token
        # Zweiter POST
        url2 = f'https://www.dresden.de/apps_ext/AbfallApp/wastebins{jsessionid}?{token}.1-searchForm-street'
        data2 = f'street={requests.utils.quote(street)}'
        response2 = session.post(url2, headers=headers, data=data2)
        matches = re.findall(r'<option value="(\d+)"[^>]*>([^<]+)</option>', response2.text)
        result = [{'nr': nr, 'standortId': int(sid)} for sid, nr in matches]
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/ical')
def ical():
    standort = request.args.get('standort')
    von = request.args.get('von')
    bis = request.args.get('bis')
    if not standort or not von or not bis:
        return jsonify({'error': 'Missing parameters standort, von, bis'}), 400
    try:
        url = f'https://stadtplan.dresden.de/project/cardo3Apps/IDU_DDStadtplan/abfall/ical.ashx?STANDORT={standort}&DATUM_VON={von}&DATUM_BIS={bis}'
        response = requests.get(url, timeout=30)
        return response.text, 200, {'Content-Type': 'text/calendar; charset=utf-8'}
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/standortid')
def standortid():
    street = request.args.get('street')
    nr = request.args.get('nr')
    if not street or not nr:
        return jsonify({'error': 'Missing query parameters street and nr'}), 400
    try:
        session, jsessionid, token = get_session()
        headers = {
            'Wicket-Ajax': 'true',
            'Wicket-Ajax-BaseURL': f'wastebins{jsessionid}?{token}',
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        # POST 1
        url1 = f'https://www.dresden.de/apps_ext/AbfallApp/wastebins{jsessionid}?{token}.0-searchForm-street'
        data1 = f'street={requests.utils.quote(street)}'
        response1 = session.post(url1, headers=headers, data=data1)
        token = update_token(response1.text) or token
        # POST 2
        url2 = f'https://www.dresden.de/apps_ext/AbfallApp/wastebins{jsessionid}?{token}.1-searchForm-street'
        data2 = f'street={requests.utils.quote(street)}'
        response2 = session.post(url2, headers=headers, data=data2)
        token = update_token(response2.text) or token
        # Find wicketStandortId
        matches = re.findall(r'<option value="(\d+)"[^>]*>([^<]+)</option>', response2.text)
        wicket_standort_id = None
        for sid, hnr in matches:
            if hnr == nr:
                wicket_standort_id = sid
                break
        if not wicket_standort_id:
            return jsonify({'error': 'Hausnummer not found'}), 404
        # POST 3
        url3 = f'https://www.dresden.de/apps_ext/AbfallApp/wastebins{jsessionid}?{token}.0-searchForm-hnrContainer-hnr'
        data3 = f'hnrContainer:hnr={wicket_standort_id}'
        response3 = session.post(url3, headers=headers, data=data3)
        token = update_token(response3.text) or token
        # POST 4
        url4 = f'https://www.dresden.de/apps_ext/AbfallApp/wastebins{jsessionid}?{token}.0-searchForm-buttonContainer-searchLink'
        data4 = f'street={requests.utils.quote(street)}&hnrContainer:hnr={wicket_standort_id}&buttonContainer:searchLink='
        response4 = session.post(url4, headers=headers, data=data4)
        match = re.search(r'STANDORT=(\d+)', response4.text)
        if match:
            standort_id = int(match.group(1))
            return jsonify({'standortId': standort_id})
        else:
            return jsonify({'error': 'Standort ID not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
