import os
import io
import re
import json
import requests
import streamlit as st
import openai
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

# --- Rejestracja czcionek dla ReportLab (dla polskich znaków w PDF) ---
try:
    # Wymaga plików LiberationSerif-Regular.ttf i LiberationSerif-Bold.ttf
    pdfmetrics.registerFont(TTFont('Serif', 'LiberationSerif-Regular.ttf'))
    pdfmetrics.registerFont(TTFont('Serif-Bold', 'LiberationSerif-Bold.ttf'))
except Exception:
    # Domyślne czcionki na wypadek braku plików .ttf
    pdfmetrics.registerFont(TTFont('Serif', 'Helvetica'))
    pdfmetrics.registerFont(TTFont('Serif-Bold', 'Helvetica-Bold'))
    st.warning("⚠️ Nie udało się wczytać czcionek LiberationSerif. Używam domyślnych czcionek bez polskich znaków w PDF.")

# --- Wczytanie presetów stylów ilustracji ---
try:
    with open("style_presets.json", "r", encoding="utf-8") as f:
        STYLE_PROMPTS = json.load(f)
except Exception:
    STYLE_PROMPTS = {}
    st.error("Brak pliku style_presets.json.")


# --- Konfiguracja strony ---
st.set_page_config(page_title="Fabryka Opowiadań", page_icon="📚", layout="wide")
st.title("✨ Fabryka Opowiadań AI")
st.caption("Twoje miejsce do tworzenia niezapomnianych opowiadań ✨")


# --- Inicjalizacja stanu sesji ---
# Definiowanie kroków aplikacji: "start", "plan", "writing", "final"
def init_session_state():
    """Inicjalizuje wszystkie niezbędne zmienne stanu sesji."""
    defaults = {
        "step": "start",
        "api_key": "",
        "plan": None,
        "story": None,
        "scene_images": {},
        "generate_scene_idx": None,
        "regenerate_scene_idx": None,
        "num_images": 3, # Domyślna wartość
        "style": list(STYLE_PROMPTS.keys())[0] if STYLE_PROMPTS else "Bajkowy", # Domyślny styl
        "want_images": "Tak",
        
        # Ustawienia domyślne, które są kluczowe dla promptu
        "genre": "Komedia",
        "length": "2250 słów", # Klucz: słowa
        "audience": "Dziecięcy (prosty język, bajkowy)", 
        "hero": "", 
        "side_characters_count": 1,
        "side_characters_desc": "", 
        "location": "Jedno miejsce (np. tajemniczy las)",
        "prompt": "" # Główny pomysł
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_state()


# --- Funkcje pomocnicze ---

def get_preferences_prompt():
    """Zbiera wszystkie ustawienia użytkownika w jeden, priorytetowy kontekst dla AI."""
    
    # Określanie liczby scen na podstawie wybranej długości
    length_map = {
        "1500 słów": "3 krótkich rozdziałów (SCENA 1-3)",
        "2250 słów": "5 średnich rozdziałów (SCENA 1-5)",
        "3000 słów": "7 długich rozdziałów (SCENA 1-7)"
    }
    num_chapters_str = length_map.get(st.session_state.length, "standardową liczbę 5 rozdziałów (SCENA 1-5)")
    
    preferences = f"""
    PRIORYTETOWE WYMAGANIA:
    1. Długość: Opowiadanie powinno mieć długość około **{st.session_state.length}** i składać się z **{num_chapters_str}**. 
    2. Styl: Utrzymane w stylu narracji **{st.session_state.audience}** oraz gatunku **{st.session_state.genre}**.
    3. Główny bohater: **{st.session_state.hero if st.session_state.hero else 'Nieokreślony, wymyśl własnego'}**.
    4. Postacie poboczne: **{st.session_state.side_characters_count}** postacie poboczne. Opis ról: **{st.session_state.side_characters_desc if st.session_state.side_characters_desc else 'Nieokreślone, wymyśl własne'}**.
    5. Miejsce akcji: **{st.session_state.location}**.
    
    Pamiętaj, aby ściśle przestrzegać ustalonej liczby rozdziałów i ich numeracji.
    """
    return preferences.strip()


def clean_title_and_extract_number(text):
    """Czyści tekst z dodatkowych symboli Markdown (jak ##) i próbuje wyciągnąć numer sceny."""
    cleaned_text = text.replace('#', '').replace('*', '').strip()
    match = re.search(r"(\d+)", cleaned_text)
    scene_num = int(match.group(0)) if match else None
    return cleaned_text, scene_num






def create_pdf(story_text, images_data=None):
    import io
    import requests
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.utils import ImageReader

    def _get_image_bytes(images_dict, scene_no):
        """Zwraca bytes obrazka dla danej sceny (obsługuje klucze str/int i różne formaty wartości)."""
        if not images_dict:
            return None

        cand_keys = [str(scene_no), scene_no]  # np. "1" i 1
        val = None
        for ck in cand_keys:
            if ck in images_dict:
                val = images_dict[ck]
                break

        if val is None:
            return None

        # 1️⃣ dict z 'buffer'
        if isinstance(val, dict) and 'buffer' in val:
            v = val['buffer']
            if isinstance(v, bytes):
                return v
            if hasattr(v, "read"):
                v.seek(0)
                return v.read()
            return None

        # 2️⃣ surowe bajty
        if isinstance(val, (bytes, bytearray)):
            return bytes(val)

        # 3️⃣ BytesIO
        if hasattr(val, "read"):
            try:
                val.seek(0)
            except Exception:
                pass
            return val.read()

        # 4️⃣ URL
        if isinstance(val, str) and val.startswith(("http://", "https://")):
            try:
                return requests.get(val, timeout=20).content
            except Exception:
                return None

        return None


    # Jeśli nie przekazano ilustracji, pobierz je z session_state
    if not images_data and "scene_images" in st.session_state:
        images_data = st.session_state.scene_images

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # --- Czcionki z polskimi znakami ---
    pdfmetrics.registerFont(TTFont("LiberationSerif", "LiberationSerif-Regular.ttf"))
    pdfmetrics.registerFont(TTFont("LiberationSerif-Bold", "LiberationSerif-Bold.ttf"))

    margin = 50
    text_width = width - 2 * margin
    y = height - margin

    # --- Nagłówek PDF ---
    pdf.setFont("LiberationSerif-Bold", 18)
    pdf.drawCentredString(width / 2, y, "Opowiadanie AI")
    y -= 40

    pdf.setFont("LiberationSerif", 12)

    lines = story_text.split("\n")
    scene_num = 0

    for line in lines:
        # --- Nowy rozdział ---
        if line.strip().lower().startswith("rozdział"):
                 
            if scene_num > 0:
                try:
                    img_bytes = _get_image_bytes(images_data, scene_num)
                    if not img_bytes:
                        continue

                    bio = io.BytesIO(img_bytes)
                    bio.seek(0)
                    img_reader = ImageReader(bio)
                    iw, ih = img_reader.getSize()
                    max_w = text_width * 0.75
                    scale = min(1.0, max_w / float(iw))
                    img_w = iw * scale
                    img_h = ih * scale

                    if y - img_h < margin:
                        pdf.showPage()
                        pdf.setFont("LiberationSerif", 12)
                        y = height - margin

                    x_center = (width - img_w) / 2
                    bio.seek(0)
                    pdf.drawImage(img_reader, x_center, y - img_h - 10, width=img_w, height=img_h)
                    y -= img_h + 30

                except Exception as e:
                    st.warning(f"⚠️ Nie udało się dodać ilustracji dla sceny {scene_num}: {e}")

            # Nowa scena
            scene_num += 1
            pdf.setFont("LiberationSerif-Bold", 14)
            pdf.drawString(margin, y, line.strip())
            y -= 25
            pdf.setFont("LiberationSerif", 12)

        else:
            # Normalny tekst
            if not line.strip():
                y -= 10
                continue
            while line:
                text_line = line[:90]
                line = line[90:]
                pdf.drawString(margin, y, text_line)
                y -= 15
                if y < margin:
                    pdf.showPage()
                    pdf.setFont("LiberationSerif", 12)
                    y = height - margin





    # --- Po ostatniej scenie — dodaj jej obraz ---
    if scene_num > 0:
        try:
            img_bytes = _get_image_bytes(images_data, scene_num)
            if not img_bytes:
                pass

            bio = io.BytesIO(img_bytes)
            bio.seek(0)
            img_reader = ImageReader(bio)
            iw, ih = img_reader.getSize()
            max_w = text_width * 0.75
            scale = min(1.0, max_w / float(iw))
            img_w = iw * scale
            img_h = ih * scale

            if y - img_h < margin:
                pdf.showPage()
                pdf.setFont("LiberationSerif", 12)
                y = height - margin

            x_center = (width - img_w) / 2
            bio.seek(0)
            pdf.drawImage(img_reader, x_center, y - img_h - 10, width=img_w, height=img_h)
            y -= img_h + 30

        except Exception as e:
            st.warning(f"⚠️ Nie udało się dodać ilustracji dla sceny {scene_num}: {e}")


    pdf.save()
    buffer.seek(0)
    return buffer








def handle_image_generation(scenes):
    """
    Logika wywołująca OpenAI Image API (DALL-E) na podstawie wskaźników z session_state.
    Wykonywana PO pętli wyświetlającej przyciski.
    """
    
    action_idx = st.session_state.get('generate_scene_idx')
    action_is_regenerate = False

    if action_idx is None:
        action_idx = st.session_state.get('regenerate_scene_idx')
        action_is_regenerate = True
    
    if action_idx is not None:
        
        # Ustalenie, która scena ma być ilustrowana (idx - 1)
        if 0 <= action_idx - 1 < len(scenes):
            scene_to_illustrate = scenes[action_idx - 1] 
        else:
            st.error(f"❌ Błąd: Numer sceny {action_idx} poza zakresem planu.")
            st.session_state['generate_scene_idx'] = None
            st.session_state['regenerate_scene_idx'] = None
            return

        with st.spinner(f"⏳ {'Generuję ponownie' if action_is_regenerate else 'Tworzę'} ilustrację dla Sceny {action_idx}..."):
            
            # Przygotowanie prompta DALL-E
            style_key = st.session_state.style
            base_prompt = STYLE_PROMPTS.get(style_key, "")
            
            # Użycie wyrażenia regularnego do usunięcia nagłówka "SCENA X:"
            clean_description = re.sub(r"(SCENA|ROZDZIAŁ)\s+\d+[:.]?\s*", "", scene_to_illustrate, flags=re.IGNORECASE).strip()
            
            # ZMODYFIKOWANY PROMPT: Zdecydowane żądanie braku tekstu i ramek
            prompt = f"""
            ABSOLUTNIE ŻADNYCH LITER, ŻADNEGO TEKSTU, ŻADNYCH NAPISÓW, ŻADNYCH RAMEK I OBRAMOWAŃ. TO JEST ILUSTRACJA DO EBOOKA.
            
            Ilustracja do ebooka, sceny opowiadania. 
            Opis sceny: {clean_description}.
            Styl graficzny: {style_key.lower()} – {base_prompt}.
            Wysoka jakość, spójny styl.
            """
            
            try:
                # Używamy DALL-E 3 (najnowszy model, generuje lepsze obrazy)
                response = openai.Image.create(
                    model="dall-e-3",
                    prompt=prompt,
                    n=1,
                    size="1024x1024"
                )

                image_url = response["data"][0]["url"]
                try:
                    img_data = requests.get(image_url, timeout=20).content
                    st.session_state.scene_images[action_idx] = img_data  # zapisujemy bajty, nie URL
                    st.success(f"✅ Ilustracja dla Sceny {action_idx} gotowa!")

                except Exception as e:
                    st.error(f"❌ Nie udało się pobrać obrazu: {e}")

            except Exception as e:
                st.error(f"❌ Błąd generowania ilustracji dla Sceny {action_idx}: {e}")

                
        st.session_state['generate_scene_idx'] = None
        st.session_state['regenerate_scene_idx'] = None
        st.rerun()


# --- Sekcja logowania API (Stały element Sidebar) ---
st.sidebar.header("🔐 Klucz API OpenAI")

if not st.session_state.api_key:
    key_input = st.sidebar.text_input("Wklej swój klucz API:", type="password", key="api_key_input")
    if key_input:
        st.session_state.api_key = key_input
        st.rerun()
    openai.api_key = None
    st.sidebar.warning("⚠️ Klucz API jest wymagany.")
else:
    openai.api_key = st.session_state.api_key
    st.sidebar.success("✅ Klucz API jest ustawiony.")
    if st.sidebar.button("🚪 Wyloguj", key="logout_btn"):
        st.session_state.api_key = ""
        # Całkowity reset, aby powrócić do kroku startowego
        keep_keys = ["api_key", "STYLE_PROMPTS"] 
        keys_to_delete = [key for key in st.session_state.keys() if key not in keep_keys]
        for key in keys_to_delete:
            del st.session_state[key]
        init_session_state() 
        st.rerun()

# -----------------------------------------------------------
# KOREKTA BŁĘDU INDEXOWANIA GATUNKU
if 'genre' in st.session_state and st.session_state.genre == 'Baśń/Fantasy':
    st.session_state.genre = 'Bajka/Baśń'
# -----------------------------------------------------------


# Blokuj działanie aplikacji bez klucza
if not st.session_state.api_key:
    st.info("Aby rozpocząć, wprowadź swój klucz API OpenAI w panelu bocznym.")
    st.stop()


# --- PANEL BOCZNY (Ustawienia Opowiadania) ---

st.sidebar.markdown("---")
st.sidebar.header("📝 Ustawienia Opowiadania")

# --- KRYTYCZNE POLE: Pomysł na Opowiadanie (TextArea) ---
st.session_state.prompt = st.sidebar.text_area(
    "GŁÓWNY POMYSŁ (np. Zajączek, który szukał zaginionej marchewki. Tytuł: Przygody zająca Fistaszka) Wypełnij bądź zostaw puste AI samo coś wybierze i wygeneruje",
    value=st.session_state.get('prompt', ''),
    height=150,
    key="sb_prompt_main"
)
st.sidebar.markdown("---")


# Używamy formularza w sidebarze, aby zachować spójność i kontrolować reruny po kliknięciu 'submit'
with st.sidebar.form("story_settings_sidebar"):
    st.markdown("Poniższe opcje pozwalają na precyzyjne ustawienie historii. **Te ustawienia są priorytetowe**.")

    st.subheader("⚙️ Opcje techniczne")
    
    # 1. Wybór Modelu GPT
    st.session_state.model = st.selectbox(
        "Model GPT do generowania:",
        ["gpt-4o-mini", "gpt-4o"],
        index=["gpt-4o-mini", "gpt-4o"].index(st.session_state.get('model', 'gpt-4o-mini')),
        key="sb_model"
    )
    
    # 2. Długość opowiadania (w słowach)
    st.session_state.length = st.selectbox(
        "Żądana długość opowiadania (wpływa na szczegółowość i liczbę scen):", 
        ["1500 słów", "2250 słów", "3000 słów"],
        index=["1500 słów", "2250 słów", "3000 słów"].index(st.session_state.get('length', '2250 słów')),
        key="sb_length"
    )

    st.markdown("---")
    st.subheader("🎭 Fabuła i Styl")
    
    # 3. Styl narracji / Grupa wiekowa
    st.session_state.audience = st.selectbox(
        "Docelowy styl narracji / Grupa wiekowa:", 
        ["Dziecięcy (prosty język, bajkowy)", "Młodzieżowy (dynamika, język potoczny)", "Dorosły (refleksyjny, głębokie tematy)"],
        index=["Dziecięcy (prosty język, bajkowy)", "Młodzieżowy (dynamika, język potoczny)", "Dorosły (refleksyjny, głębokie tematy)"].index(st.session_state.get('audience', 'Dziecięcy (prosty język, bajkowy)')),
        key="sb_audience"
    )

    # 4. Gatunek Opowiadania (Rozszerzona lista)
    st.session_state.genre = st.selectbox(
        "Gatunek opowiadania:", 
        ["Bajka/Baśń", "Fantasy", "Przygoda", "Komedia", "Horror", "Romans", "Sci-Fi", "Dramat"],
        index=["Bajka/Baśń", "Fantasy", "Przygoda", "Komedia", "Horror", "Romans", "Sci-Fi", "Dramat"].index(st.session_state.get('genre', 'Bajka/Baśń')),
        key="sb_genre_select"
    )
    
    # 5. Główny Bohater
    st.session_state.hero = st.text_input(
        "Kim jest główny bohater? (np. Odważny rycerz imieniem Jan lub Pies Pucek)",
        value=st.session_state.get('hero', ''),
        key="sb_hero"
    )

    # 6. Postacie Poboczne (Licznik i Opis)
    st.session_state.side_characters_count = st.slider(
        "Liczba postaci pobocznych:",
        min_value=0,
        max_value=5,
        value=st.session_state.get('side_characters_count', 1),
        key="sb_side_count"
    )

    st.session_state.side_characters_desc = st.text_area(
        "Opis ról postaci pobocznych (np. Wredny kot, który chce ukraść marchewkę):",
        value=st.session_state.get('side_characters_desc', ''),
        height=80,
        key="sb_side_desc"
    )

    # 7. Miejsce Akcji
    st.session_state.location = st.selectbox(
        "Ograniczenie miejsca akcji:", 
        ["Jedno miejsce (np. tajemniczy las)", "Dwa miejsca (np. miasto i góry)", "Losowo (zostaw AI)"],
        index=["Jedno miejsce (np. tajemniczy las)", "Dwa miejsca (np. miasto i góry)", "Losowo (zostaw AI)"].index(st.session_state.get('location', 'Jedno miejsce (np. tajemniczy las)')),
        key="sb_location"
    )


    st.markdown("---")
    st.subheader("🎨 Ilustracje (DALL-E)")

    # 8. Czy chcesz ilustracje?
    st.session_state.want_images = st.radio(
        "Czy chcesz ilustracje do opowiadania?",
        ["Tak", "Nie"],
        index=["Tak", "Nie"].index(st.session_state.get('want_images', 'Tak')),
        key="sb_want_images"
    )
    
    # 9. Ustawienia ilustracji (pokazujemy tylko, jeśli wybrano 'Tak')
    if st.session_state.want_images == "Tak":
        image_options = list(STYLE_PROMPTS.keys())
        st.session_state.style = st.selectbox(
            "Styl ilustracji:",
            image_options,
            index=image_options.index(st.session_state.get('style', 'Bajkowy')),
            key="sb_style"
        )
        
        # Używamy suwaka do liczby, ale AI będzie ograniczać to do liczby rozdziałów
        st.session_state.num_images = st.slider(
            "Maksymalna liczba ilustracji (na tyle rozdziałów, ile będzie w planie):",
            min_value=1,
            max_value=9,
            value=st.session_state.get('num_images', 5),
            key="sb_num_images"
        )
    else:
        st.session_state.num_images = 0
        st.session_state.style = None


    # Przycisk zatwierdzający formularz
    submitted_settings = st.form_submit_button("Start! Generuj Plan Opowiadania 🚀", type="primary")


# Logika generowania planu (działa niezależnie od kroku, ale resetuje historię)
if submitted_settings:
    # Reset historii po zmianie parametrów
    st.session_state.plan = None
    st.session_state.story = None
    st.session_state.scene_images = {}
    st.session_state.step = "start" # Zawsze wracamy na start po zmianie ustawień

    with st.spinner("✍️ Tworzę plan wydarzeń..."):
        
        # Obliczanie oczekiwanej liczby scen na podstawie długości
        scene_count = 3 if "1500" in st.session_state.length else 5 if "2250" in st.session_state.length else 7
        
        # --- Użycie Priorytetowych Preferencji ---
        preferences = get_preferences_prompt()
        
        # --- INSTRUKCJA DOT. STRUKTURY TRÓJDZIELNEJ ---
        structure_prompt = f"""
        Podziel plan na klasyczną strukturę trójdzielną (Akt I - Rozpoczęcie, Akt II - Rozwinięcie, Akt III - Zakończenie). 
        Zachowaj proporcje: Akt I (ok. 25% scen), Akt II (ok. 50% scen), Akt III (ok. 25% scen). 
        W planie NIE używaj nagłówków Akt I, Akt II, Akt III. Po prostu ułóż sceny w tej logicznej kolejności.
        """
        
        prompt = f"""
        {preferences}
        
        GŁÓWNY POMYSŁ: **{st.session_state.prompt}**
        
        Na podstawie powyższych PRIORYTETOWYCH WYMAGAŃ i głównego pomysłu:
        
        1. Stwórz plan opowiadania, który będzie miał **dokładnie {scene_count} punktów** (SCENA 1–{scene_count}).
        2. {structure_prompt}
        3. Każdy punkt ma zawierać maksymalnie 3 zdania opisujące kluczowe wydarzenia.
        4. Opisz scenę tak, aby była łatwa do zilustrowania.

        Format odpowiedzi (ZACZNIJ OD PIERWSZEJ SCENY, BEZ DODATKOWEGO TEKSTU WSTĘPNEGO):
        SCENA 1: ...
        SCENA 2: ...
        ...
        SCENA {scene_count}: ...
        """
        
        try:
            response = openai.ChatCompletion.create(
                model=st.session_state.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1500,
                temperature=0.8
            )
            
            st.session_state.plan = response.choices[0].message["content"]
            st.session_state.step = "plan"
            st.success("Plan opowiadania gotowy!")
        
        except Exception as e:
            st.error(f"❌ Wystąpił błąd podczas generowania planu: {e}")
            st.session_state.step = "start"

        st.rerun()

# --- WIDOK GŁÓWNY W ZALEŻNOŚCI OD KROKU ---

# KROK 1: START (Wyświetlanie tylko komunikatu oczekiwania na plan)
if st.session_state.step == "start":
    st.header("1. Czekam na plan opowiadania")
    st.info("Wprowadź wszystkie szczegóły w panelu bocznym i naciśnij 'Generuj Plan Opowiadania 🚀', aby kontynuować.")


# --- KROK 2: PLAN (Wyświetlanie i generowanie ilustracji) ---
if st.session_state.step == "plan" and st.session_state.plan:
    st.header("2. Akceptacja planu i ilustracje")
    st.caption("Przejrzyj plan, wygeneruj ilustracje (jeśli wybrano) i przejdź do pisania historii.")
    st.divider()

    # --- Ekstrakcja scen ---
    scenes_raw = [line.strip() for line in st.session_state.plan.split("\n") if line.strip()]
    # Używamy re.match, aby być odpornym na SCENA lub ROZDZIAŁ
    scenes = [s for s in scenes_raw if re.match(r"(SCENA|ROZDZIAŁ)\s+\d+", s.upper())]
    
    total_images = st.session_state.num_images
    current_images = len(st.session_state.scene_images)
    
    if st.session_state.want_images == "Tak":
        st.progress(current_images / total_images)
        st.caption(f"Ilustracje: **{current_images}/{total_images}** (Styl: {st.session_state.style})")
        st.markdown("---")
    
    # --- Pętla wyświetlająca sceny i przyciski ---
    for idx, scene in enumerate(scenes, start=1):
        clean_scene_display = scene.replace('###', '').replace('"', '').strip()
        st.markdown(f"**{clean_scene_display}**") # Usuwamy prefix idx., bo jest w tekście Scena X:
        
        col1, col2 = st.columns([0.3, 0.7])
        
        # LOGIKA PRZYCISKÓW (ustawia stan sesji poprzez callback)
        if st.session_state.want_images == "Tak":
            with col1:
                if idx in st.session_state.scene_images:
                    # Przycisk regeneracji
                    st.button(
                        f"🔁 Wygeneruj ponownie ({idx})", 
                        key=f"regen_{idx}",
                        on_click=lambda i=idx: st.session_state.__setitem__('regenerate_scene_idx', i),
                        help="Wygeneruj nową ilustrację."
                    )
                elif current_images < total_images:
                    # Przycisk generowania
                    st.button(
                        f"🎨 Generuj ilustrację ({idx})", 
                        key=f"gen_{idx}",
                        on_click=lambda i=idx: st.session_state.__setitem__('generate_scene_idx', i),
                        help="Generuje nową ilustrację."
                    )
                else:
                    st.info("Limit ilustracji osiągnięty.")
                        
            # Wyświetlenie obrazka
            with col2:
                if idx in st.session_state.scene_images:
                    st.image(
                        st.session_state.scene_images[idx],
                        caption=f"Ilustracja {idx} – {st.session_state.style}",
                        use_column_width="auto"
                    )
        
        st.markdown("---")

    # FAKTYCZNE WYWOŁANIE API (poza pętlą, na końcu kroku)
    if st.session_state.want_images == "Tak":
        handle_image_generation(scenes)



    # PRZYCISK PRZEJŚCIA DALEJ
    st.markdown("---")
    if st.button("✍️ Akceptuję plan i przejdź do pisania", key="go_to_writing_clean"):
        # 🔹 Zapisz kopię ilustracji z planu i ujednolić klucze na stringi ("1","2",...)
        if 'scene_images' in st.session_state and st.session_state.scene_images:
            normalized = {}
            for k, v in st.session_state.scene_images.items():
                key_str = str(k)
                # v może być: bytes, BytesIO, URL (str), albo dict z 'buffer'
                if isinstance(v, dict) and 'buffer' in v:
                    normalized[key_str] = v['buffer']
                else:
                    normalized[key_str] = v
            st.session_state.story_images = normalized
            st.write("✅ Ilustracje zapisane do story_images:", list(st.session_state.story_images.keys()))
        else:
            st.warning("⚠️ Brak ilustracji w scene_images — PDF będzie bez obrazków.")

        st.session_state.step = "writing"
        st.session_state['generate_scene_idx'] = None
        st.session_state['regenerate_scene_idx'] = None
        st.rerun()



# --- KROK 3: WRITING (Generowanie pełnej historii) ---
if st.session_state.step == "writing":
    st.header("3. Generowanie i edycja historii")
    
    if st.session_state.story is None:
        
        with st.spinner("⏳ Piszę pełne opowiadanie na podstawie zaakceptowanego planu... To może potrwać do minuty. Proszę nie odświeżać strony."):
            
            # --- Użycie Priorytetowych Preferencji ---
            preferences = get_preferences_prompt()
            
            prompt = f"""
            {preferences}
            
            GŁÓWNY POMYSŁ: **{st.session_state.prompt}**
            
            Na podstawie powyższych PRIORYTETOWYCH WYMAGAŃ i głównego pomysłu, oraz poniższego planu, napisz pełne, spójne opowiadanie.
            
            Pamiętaj:
            - **Zachowaj klasyczną strukturę trójdzielną (rozpoczęcie, rozwinięcie, zakończenie) zgodnie z planem poniżej.**
            - **Ściśle przestrzegaj długości i liczby rozdziałów.**
            - **ROZWINIĘCIE KAŻDEJ SCENY: Pamiętaj, że opowiadanie ma być długie (1500-3000 słów). KAŻDA SCENA musi być rozbudowana, szczegółowa i zawierać dialogi. Nie poprzestawaj na 2-3 akapitach na scenę.**
            - **Użyj bohatera i stylu zdefiniowanego w PRIORYTETOWYCH WYMAGANIACH.**
            - Każdą nową scenę zacznij dokładnie od nagłówka ROZDZIAŁ X: (gdzie X to numer sceny) w oddzielnej linii. Oddzielaj akapity pustą linią.
            
            Plan do wykorzystania (już ułożony w kolejności Akt I, II, III):
            ---
            {st.session_state.plan}
            ---
            """
            
            try:
                response = openai.ChatCompletion.create(
                    model=st.session_state.model, 
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=3500, # Max tokenów dla GPT-4o, aby pozwolić na długie opowieści
                    temperature=0.7
                )
                st.session_state.story = response.choices[0].message["content"]
                st.success("Opowiadanie gotowe!")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Błąd podczas pisania historii. Spróbuj ponownie. Błąd: {e}")
                st.session_state.step = "plan"
                st.rerun()

    # Wyświetlenie i edycja opowiadania
    if st.session_state.story:
        st.markdown("---")
        st.subheader("Ostatnie poprawki")
        
        st.session_state.story = st.text_area(
            "Edytuj opowiadanie, aby dopracować szczegóły. Nie usuwaj nagłówków ROZDZIAŁ X:",
            st.session_state.story,
            height=600,
            key="final_story_editor"
        )
        
        st.markdown("---")
        colC, colD = st.columns(2)
        with colC:
            if st.button("⬅️ Wróć do planu i ilustracji", key="back_to_plan"):
                st.session_state.step = "plan"
                st.rerun()

        with colD:
            if st.button("💾 Zakończ i generuj PDF", key="go_to_final"):
                st.session_state.step = "final"
                st.rerun()


# --- KROK 4: FINAL (Pobieranie i podsumowanie) ---
if st.session_state.step == "final":
    st.header("4. Opowiadanie gotowe!")
    st.success("Twoja historia została pomyślnie stworzona i jest gotowa do pobrania jako PDF.")
    st.markdown("---")
    
    st.subheader("Pobieranie pliku PDF")
    
    if st.session_state.story:
        # (opcjonalny debug) – pokazuje, co mamy w pamięci
        # st.write("🧩 Debug: scene_images:", st.session_state.get('scene_images', {}))
        # st.write("🧩 Debug: story_images:", st.session_state.get('story_images', {}))

        with st.spinner("Przygotowuję PDF (tekst + ilustracje)..."):
            # Najpierw próbujemy użyć zapisanych ilustracji z planu
            images_to_use = st.session_state.get('story_images', st.session_state.get('scene_images', {}))

            # Debug — sprawdzamy, czy PDF faktycznie widzi obrazki
            if images_to_use:
                st.write("🖼️ Ilustracje dostępne dla PDF:", list(images_to_use.keys()))
            else:
                st.warning("⚠️ Brak zapisanych ilustracji — PDF będzie bez obrazków.")

            # Tworzymy PDF z właściwym zestawem ilustracji
            pdf_buffer = create_pdf(
                st.session_state.story,
                images_to_use
            )


        st.download_button(
            label="📥 Kliknij tutaj, aby pobrać opowiadanie jako PDF (tekst + obrazy)",
            data=pdf_buffer,
            file_name="fabryka_opowiadan.pdf",
            mime="application/pdf"
        )

    st.markdown("---")
    
    col_final_1, col_final_2 = st.columns(2)
    with col_final_1:
        if st.button("✏️ Wróć do edycji tekstu", key="edit_story_final"):
            st.session_state.step = "writing"
            st.rerun()

    with col_final_2:
        if st.button("🔄 Stwórz nowe opowiadanie", key="new_story_final"):
            # Zachowaj tylko klucz API i presety stylów, resztę usuń
            keep_keys = ["api_key", "STYLE_PROMPTS"] 
            keys_to_delete = [key for key in st.session_state.keys() if key not in keep_keys]
            for key in keys_to_delete:
                del st.session_state[key]
            init_session_state() 
            st.rerun()