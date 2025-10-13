# ✨ Fabryka Opowiadań

Aplikacja AI, która tworzy krótkie opowiadania z pomysłu użytkownika —  
od zarysu fabuły po gotowy tekst i ilustracje generowane przez sztuczną inteligencję.  
Zaprojektowana w Streamlit z wykorzystaniem modeli OpenAI (GPT-4o/GPT4omini + DALL·E). 📚🎨  

---

## 🚀 Funkcje

- 🧠 Generowanie zarysu i planu opowiadania na podstawie pomysłu użytkownika  
- ✍️ Tworzenie pełnej historii w wybranym stylu narracji i gatunku  
- 🎨 Generowanie ilustracji w różnych stylach (bajkowy, pastelowy, realistyczny, komiksowy, kolorowanka)  
- 💾 Eksport gotowego opowiadania do pliku PDF


---

## 🧩 Technologie

- **Python 3.10+**  
- **Streamlit** – interfejs webowy  
- **OpenAI API** – generowanie tekstu i ilustracji  
- **ReportLab** – tworzenie pliku PDF  
- **Pillow, Requests** – obsługa obrazów  

---

## ⚙️ Uruchomienie lokalne

```bash
git clone https://github.com/<twoj_login>/fabryka-opowiadan.git
cd fabryka-opowiadan
pip install -r requirements.txt
streamlit run app.py
