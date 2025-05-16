
import io 
import requests
from flask import Flask, request, jsonify, send_from_directory
import mysql.connector
import openai
import os
from config import OPENAI_API_KEY, ELEVENLABS_API_KEY

openai.api_key = OPENAI_API_KEY

app = Flask(__name__, static_folder='public', static_url_path='')

db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '1234',
    'database': 'pharmacy_db'
}

def get_db_connection():
    try:
        conn = mysql.connector.connect(**db_config)
        return conn
    except mysql.connector.Error as err:
        print("Database connection error:", err)
        return None

def get_exact_medication_info(query):
    conn = get_db_connection()
    if not conn:
        return None
    cursor = conn.cursor(dictionary=True)
    sql = '''
        SELECT type_id, name, generic_name, `class`, indication, frequency, max_dose,
               contraindications, drug_interactions, pregnancy_safety, side_effects, high_risk, hazard
        FROM medications
        WHERE LOWER(name) = LOWER(%s)
           OR LOWER(SUBSTRING_INDEX(name, ' ', 1)) = LOWER(%s)
    '''
    try:
        q = query.strip()
        cursor.execute(sql, (q, q))
        results = cursor.fetchall()
    except mysql.connector.Error as err:
        print("MySQL Error (exact match):", err)
        results = None
    cursor.close()
    conn.close()
    return results

def get_partial_medication_info(query):
    conn = get_db_connection()
    if not conn:
        return None
    cursor = conn.cursor(dictionary=True)
    sql = '''
        SELECT type_id, name, generic_name, `class`, indication, frequency, max_dose,
               contraindications, drug_interactions, pregnancy_safety, side_effects, high_risk, hazard
        FROM medications
        WHERE name LIKE %s OR generic_name LIKE %s
    '''
    like_pattern = f"%{query.strip()}%"
    try:
        cursor.execute(sql, (like_pattern, like_pattern))
        results = cursor.fetchall()
    except mysql.connector.Error as err:
        print("MySQL Error (partial match):", err)
        results = None
    cursor.close()
    conn.close()
    return results

def format_medication_info(med):
    high_risk_str = "Yes" if med['high_risk'] in [1, True, "1"] else "No"
    hazard_str = "Yes" if med['hazard'] in [1, True, "1"] else "No"
    
    return (
        f"Name: {med['name']}\n"
        f"Generic Name: {med['generic_name']}\n"
        f"Class: {med['class']}\n"
        f"Indication: {med['indication']}\n"
        f"Frequency: {med['frequency']}\n"
        f"Max Dose: {med['max_dose']}\n"
        f"Contraindications: {med['contraindications']}\n"
        f"Drug Interactions: {med['drug_interactions']}\n"
        f"Pregnancy Safety: {med['pregnancy_safety']}\n"
        f"Side Effects: {med['side_effects']}\n"
        f"High Risk: {high_risk_str}\n"
        f"Hazard: {hazard_str}"
    )

def get_answer_from_openai(query):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are PharmeXa, an advanced medical assistant specialized in drug information. "
                        "Answer questions clearly, politely, and always introduce yourself as PharmeXa."
                    )
                },
                {"role": "user", "content": query}
            ],
            max_tokens=200
        )
        return response['choices'][0]['message']['content']
    except openai.error.OpenAIError as e:
        print("OpenAI Error:", e)
        return "Sorry, I couldn't fetch an answer right now."

@app.route('/get-answer', methods=['POST'])
def get_answer():
    try:
        data = request.get_json()
        query = data.get('query', '').strip()
        if not query:
            return jsonify({"error": "No query provided."}), 400

        lowered_query = query.lower()

        if any(greet in lowered_query for greet in ["hello", "hi", "hey"]):
            return jsonify({"answer": "Hello! I'm PharmeXa, your AI drug assistant. How can I help you?"})

        if any(keyword in lowered_query for keyword in ["developer", "who made you", "creator"]):
            return jsonify({"answer": "I'm developed by Maha Faleh Alqahtani, a software developer."})

        found_medications = []
        words_in_query = query.split()

        for word in words_in_query:
            exact = get_exact_medication_info(word)
            if exact:
                found_medications.extend(exact)

        if not found_medications:
            for word in words_in_query:
                partial = get_partial_medication_info(word)
                if partial:
                    found_medications.extend(partial)

        unique_meds = {med['name']: med for med in found_medications}.values()
        if unique_meds:
            meds = list(unique_meds)
            if len(meds) == 1:
                return jsonify({"answer": format_medication_info(meds[0])})
            else:
                options = "\n\n".join(
                    f"Option {i} - Name: {m['name']}, Generic: {m['generic_name']}" 
                    for i, m in enumerate(meds, 1)
                )
                return jsonify({"answer": f"Multiple medications found:\n\n{options}\n\nPlease clarify."})

        return jsonify({"answer": get_answer_from_openai(query)})

    except Exception as e:
        print("Error:", e)
        return jsonify({"error": "An error occurred."}), 500

@app.route('/medications', methods=['GET'])
def get_medications():
    sql = '''
        SELECT m.medication_id, m.name, m.generic_name, m.class, m.indication,
               m.frequency, m.max_dose, m.contraindications, m.drug_interactions,
               m.pregnancy_safety, m.side_effects, m.high_risk, m.hazard, t.type_name
        FROM medications m
        JOIN medication_types t ON m.type_id = t.type_id
    '''
    try:
        conn = get_db_connection()
        if not conn:
            return "DB connection error", 500
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql)
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(results)
    except Exception as e:
        print("Error in GET /medications:", e)
        return "Error", 500

@app.route('/')
def home():
    return send_from_directory('public', 'index.html')

if __name__ == "__main__":
    app.run(debug=True)
