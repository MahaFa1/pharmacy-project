import io
import requests
from flask import Flask, request, jsonify, send_from_directory
import mysql.connector
import openai
import os
openai.api_key = os.getenv("OPENAI_API_KEY")
elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY")

app = Flask(__name__, static_folder='public', static_url_path='')

# إعداد OpenAI API – استبدل المفتاح بمفتاحك الخاص

# إعدادات قاعدة البيانات MySQL
db_config = {
    'host': 'nozomi.proxy.rlwy.net',
    'user': 'root',
    'password': 'IfKQkXDNTONZBtEQCYWwWHTqDRdtSnbV',
    'database': 'railway',
    'port': 31645
}


def get_db_connection():
    try:
        conn = mysql.connector.connect(**db_config)
        return conn
    except mysql.connector.Error as err:
        print("Database connection error:", err)
        return None

def get_exact_medication_info(query):
    """
    تبحث عن معلومات الدواء التي تطابق الاسم كاملًا أو تطابق الكلمة الأولى من الاسم (غير حساس للحالة).
    تُعيد قائمة بالنتائج (list of dicts).
    """
    conn = get_db_connection()
    if not conn:
        return None
    cursor = conn.cursor(dictionary=True)
    sql = """
        SELECT type_id, name, generic_name, `class`, indication, frequency, max_dose,
               contraindications, drug_interactions, pregnancy_safety, side_effects, high_risk, hazard
        FROM medications
        WHERE LOWER(name) = LOWER(%s)
           OR LOWER(SUBSTRING_INDEX(name, ' ', 1)) = LOWER(%s)
    """
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
    """
    تبحث عن معلومات الدواء باستخدام بحث جزئي (LIKE).
    تُعيد قائمة بالنتائج (list of dicts).
    """
    conn = get_db_connection()
    if not conn:
        return None
    cursor = conn.cursor(dictionary=True)
    sql = """
        SELECT type_id, name, generic_name, `class`, indication, frequency, max_dose,
               contraindications, drug_interactions, pregnancy_safety, side_effects, high_risk, hazard
        FROM medications
        WHERE name LIKE %s OR generic_name LIKE %s
    """
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
    """
    يُرجع نصاً منسقاً بشكل أنيق لعرض معلومات دواء مفرد.
    تُحوّل قيم high_risk و hazard إلى "Yes" إذا كانت 1 وإلى "No" إذا كانت 0.
    """
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

from openai import OpenAI

client = OpenAI()

def get_answer_from_openai(query):
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are PharmeXa, an advanced medical information program specialized in answering questions about medical drugs. "
                        "Provide concise and accurate information. Always identify yourself as PharmeXa."
                    )
                },
                {"role": "user", "content": query}
            ],
            max_tokens=150
        )
        answer = response.choices[0].message.content
        return answer
    except Exception as e:
        print("OpenAI API Error:", e)
        return "An error occurred while fetching the answer from OpenAI."

@app.route('/get-answer', methods=['POST'])
def get_answer():
    try:
        data = request.get_json()
        query = data.get('query', '').strip()

        if not query:
            return jsonify({"error": "No query provided."}), 400

        # نحاول نبحث أولاً في قاعدة البيانات
        words_in_query = query.split()
        found_medications = []

        for word in words_in_query:
            exact_results = get_exact_medication_info(word)
            if exact_results:
                found_medications.extend(exact_results)

        if not found_medications:
            for word in words_in_query:
                partial_results = get_partial_medication_info(word)
                if partial_results:
                    found_medications.extend(partial_results)

        unique_medications = {med['name']: med for med in found_medications}.values()

        if unique_medications:
            medications = list(unique_medications)
            if len(medications) == 1:
                formatted = format_medication_info(medications[0])
                return jsonify({"answer": formatted})
            else:
                options = "\n\n".join(
                    f"Option {idx}:\n"
                    f"Name: {med['name']}\n"
                    f"Generic: {med['generic_name']}\n"
                    f"Class: {med['class']}\n"
                    f"Indication: {med['indication']}\n"
                    f"Frequency: {med['frequency']}\n"
                    f"Max Dose: {med['max_dose']}"
                    for idx, med in enumerate(medications, start=1)
                )
                return jsonify({"answer": f"Multiple medications found:\n\n{options}\n\nPlease specify exactly which one you meant."})

        # إذا ما وجدنا أي دواء، نرسل السؤال لـ OpenAI
        answer = get_answer_from_openai(query)
        return jsonify({"answer": answer})

    except Exception as e:
        print("Error in /get-answer:", e)
        return jsonify({"error": "An error occurred while processing your request."}), 500

@app.route('/medications', methods=['GET'])
def get_medications():
    const_query = """
        SELECT m.medication_id, m.name, m.generic_name, m.class, m.indication,
               m.frequency, m.max_dose, m.contraindications, m.drug_interactions,
               m.pregnancy_safety, m.side_effects, m.high_risk, m.hazard, t.type_name
        FROM medications m
        JOIN medication_types t ON m.type_id = t.type_id
    """
    try:
        conn = get_db_connection()
        if not conn:
            return "Database connection error", 500
        cursor = conn.cursor(dictionary=True)
        cursor.execute(const_query)
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(results)
    except Exception as e:
        print("Error in /medications:", e)
        return "Error", 500

@app.route('/medications', methods=['POST'])
def add_medication():
    data = request.get_json()
    sql = """
        INSERT INTO medications (type_id, name, generic_name, class, indication,
                                   frequency, max_dose, contraindications, drug_interactions,
                                   pregnancy_safety, side_effects, high_risk, hazard)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    values = (
        data.get('type_id'),
        data.get('name'),
        data.get('generic_name'),
        data.get('class'),
        data.get('indication'),
        data.get('frequency'),
        data.get('max_dose'),
        data.get('contraindications'),
        data.get('drug_interactions'),
        data.get('pregnancy_safety'),
        data.get('side_effects'),
        data.get('high_risk') or False,
        data.get('hazard')
    )
    try:
        conn = get_db_connection()
        if not conn:
            return "Database connection error", 500
        cursor = conn.cursor()
        cursor.execute(sql, values)
        conn.commit()
        cursor.close()
        conn.close()
        return "تمت إضافة الدواء بنجاح", 201
    except Exception as e:
        print("Error in POST /medications:", e)
        return "Error", 500

@app.route('/')
def home():
    return send_from_directory('public', 'index.html')

if __name__ == "__main__":
    app.run(debug=True)
