import io
import requests
from flask import Flask, request, jsonify, send_from_directory
import mysql.connector
import openai
import os

openai.api_key = os.getenv("OPENAI_API_KEY")
elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY")

app = Flask(__name__, static_folder='public', static_url_path='')

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

def get_medication_by_property(query):
    """
    تحلل الاستعلام لتحديد ما إذا كان يحتوي على خاصية معينة مثل "الآثار الجانبية لدواء X".
    تعيد الاسم والخاصية المطلوبة إن وجدت.
    """
    properties = {
        'الآثار الجانبية': 'side_effects',
        'الاستخدام': 'indication',
        'الجرعة': 'max_dose',
        'التكرار': 'frequency',
        'التفاعلات الدوائية': 'drug_interactions',
        'الأمان في الحمل': 'pregnancy_safety',
        'الأعراض الجانبية': 'side_effects',
        'الموانع': 'contraindications',
        'نوع الدواء': 'class'
    }
    for label, field in properties.items():
        if label in query:
            words = query.split()
            for word in words:
                if word not in label:
                    return word, field
    return None, None

def get_specific_property(med_name, field):
    conn = get_db_connection()
    if not conn:
        return None
    cursor = conn.cursor(dictionary=True)
    sql = f"""
        SELECT {field} FROM medications
        WHERE LOWER(name) LIKE %s OR LOWER(generic_name) LIKE %s
    """
    like_pattern = f"%{med_name.lower()}%"
    cursor.execute(sql, (like_pattern, like_pattern))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result[field] if result else None

def get_all_medications():
    conn = get_db_connection()
    if not conn:
        return []
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT name FROM medications")
    result = [row['name'] for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return result

def get_exact_medication_info(query):
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
                    "content": "You are PharmeXa, an advanced assistant for drug information."
                },
                {"role": "user", "content": query}
            ],
            max_tokens=150
        )
        return response['choices'][0]['message']['content']
    except Exception as e:
        print("OpenAI API Error:", e)
        return "I couldn't find the information."

@app.route('/get-answer', methods=['POST'])
def get_answer():
    try:
        data = request.get_json()
        query = data.get('query', '').strip()

        if not query:
            return jsonify({"error": "No query provided."}), 400

        # استخراج خاصية معينة إذا وُجدت
        med_name, field = get_medication_by_property(query)
        if med_name and field:
            value = get_specific_property(med_name, field)
            if value:
                return jsonify({"answer": f"{field.replace('_', ' ').capitalize()} for {med_name}: {value}"})

        # في حال لم يُذكر اسم دواء – نعرض الكل
        if 'كل' in query or 'الأدوية' in query:
            meds = get_all_medications()
            return jsonify({"answer": "\n".join(meds)})

        # بحث عادي – دقيق وجزئي
        found_medications = []
        for word in query.split():
            exact = get_exact_medication_info(word)
            if exact:
                found_medications.extend(exact)
        if not found_medications:
            for word in query.split():
                partial = get_partial_medication_info(word)
                if partial:
                    found_medications.extend(partial)
        unique_medications = {med['name']: med for med in found_medications}.values()
        if unique_medications:
            meds = list(unique_medications)
            if len(meds) == 1:
                return jsonify({"answer": format_medication_info(meds[0])})
            else:
                options = "\n\n".join(
                    f"Option {idx}:\nName: {med['name']}\nClass: {med['class']}\nIndication: {med['indication']}"
                    for idx, med in enumerate(meds, start=1))
                return jsonify({"answer": f"Multiple medications found:\n\n{options}"})

        # إذا ما لقينا شيء – نستخدم GPT
        return jsonify({"answer": get_answer_from_openai(query)})

    except Exception as e:
        print("Error in /get-answer:", e)
        return jsonify({"error": "An error occurred while processing your request."}), 500

@app.route('/')
def home():
    return send_from_directory('public', 'index.html')

if __name__ == "__main__":
    app.run(debug=True)