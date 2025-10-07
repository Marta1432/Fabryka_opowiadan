import os
import streamlit as st
import openai
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io
import requests
from PIL import Image
# --- Wczytanie presetów stylów ilustracji ---
import json

try:
    with open("style_presets.json", "r", encoding="utf-8") as f:
        STYLE_PROMPTS = json.load(f)
except Exception as e:
    st.error(f"Nie udało się wczytać pliku stylów: {e}")
    STYLE_PROMPTS = {}




# --- Konfiguracja strony ---
st.set_page_config(page_title="Fabryka Opowiadań", page_icon="📚")
st.caption("Twoje miejsce do tworzenia magicznych historii ✨")


# --- Sekcja logowania API ---
if "api_key" not in st.session_state:
    st.session_state.api_key = ""

st.sidebar.header("🔐 Klucz API OpenAI")

# Jeśli klucz już istnieje → nie pokazuj pola, tylko komunikat
if st.session_state.api_key:
    st.sidebar.success("✅ Klucz API został zapisany.")
    if st.sidebar.button("🚪 Wyloguj"):
        st.session_state.api_key = ""
        st.rerun()
else:
    st.sidebar.write("Aby korzystać z aplikacji, wklej swój klucz API (nie jest on nigdzie zapisywany).")
    api_input = st.sidebar.text_input("Wprowadź swój OpenAI API key:", type="password")

    if api_input:
        st.session_state.api_key = api_input
        openai.api_key = api_input
        st.rerun()  # natychmiast odświeża stronę, żeby ukryć pole
    else:
        st.warning("⚠️ Wprowadź swój klucz API w panelu bocznym, aby rozpocząć.")
        st.stop()



# --- SIDEBAR ---
st.sidebar.header("⚙️ Ustawienia opowiadania")
model = st.sidebar.selectbox("🤖 Wybierz model", ["gpt-4o-mini", "gpt-4o"])
st.sidebar.markdown("### 🧩 Dane wejściowe fabuły")
st.sidebar.caption(
    "Uzupełnij według własnych preferencji lub pozostaw puste pola. ✨"
    "Im więcej podasz szczegółów, tym bardziej dopasowana będzie opowieść. ✨"
)





length_option = st.sidebar.selectbox(
    "📏 Długość historii",
    ["Krótka (~3000 słów)", "Średnia (~4500 słów)", "Długa (~6000 słów)"]
)
length_map = {"Krótka (~3000 słów)": 3000, "Średnia (~4500 słów)": 4500, "Długa (~6000 słów)": 6000}
target_words = length_map[length_option]
target_tokens = int(target_words * 1.5)

idea = st.sidebar.text_area(
    "✍️ Pomysł na opowiadanie",
    value=st.session_state.get("idea", "")
)



# --- Styl języka i sposób narracji ---
language_style = st.sidebar.selectbox(
    "🗣️ Styl narracji",
    [
        "Dziecięcy – prosty język, krótkie zdania, ciepły morał",
        "Młodzieżowy – żywe tempo, emocje, humor lub napięcie",
        "Dorosły – naturalny język, refleksyjny ton, symbolika lub realizm"
    ]
)
clean_language = language_style.split("–")[0].strip().lower()

# --- Bohater główny ---
hero_identity = st.sidebar.text_area(
    "🦸‍♀️ Kim jest główny bohater?",
    placeholder="Np. Młody lisek marzący o podróżach, Fantastyczne przygody, straszne i mroczne historie..."
)

# --- Postacie poboczne ---
side_count = st.sidebar.slider("👥 Ilość postaci pobocznych", 0, 7, 1)
side_characters = st.sidebar.text_area(
    "✏️ Kim są postacie poboczne?",
    placeholder="Np. przyjaciel z lasu, nauczyciel, starsza sąsiadka...",
    height=100 + (side_count * 15)  # dynamicznie zwiększa pole, jeśli postaci jest więcej
)

# --- Miejsce akcji ---
place_option = st.sidebar.radio(
    "🌍 Miejsce akcji",
    ["Jedno miejsce", "Wiele miejsc", "Losowe"]
)

# --- Gatunek ---
genre = st.sidebar.selectbox(
    "🎭 Gatunek opowieści",
    ["Bajka", "Fantasy", "Przygoda", "Komedia", "Horror", "Romans", "Thriller", "Sci-Fi", "Dramat"]
)

# --- Podgląd zarysu opowiadania ---
if st.sidebar.button("🔍 Sprawdź zarys opowiadania"):
    with st.spinner("Generuję krótki zarys historii... ✨"):
        prompt = f"""
        Napisz bardzo krótki zarys (2–3 zdania) opowiadania.
        Gatunek: {genre}.
        Styl narracji: {language_style.lower()}.
        Bohater: {hero_identity if hero_identity else "brak opisu"}.
        Postacie poboczne: {side_characters if side_characters else "brak"}.
        Miejsce akcji: {place_option}.
        Pisz w sposób ciekawy, zachęcający do poznania dalszej historii.
        """
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        summary = response.choices[0].message["content"]
        st.sidebar.info(f"📝 **Zarys opowiadania:**\n\n{summary}")

        st.session_state.summary = summary




# --- MAIN PANEL ---
st.title("📚 Fabryka Opowiadań")

if "plan" not in st.session_state:
    st.session_state.plan = None
if "story_parts" not in st.session_state:
    st.session_state.story_parts = []
if "step" not in st.session_state:
    st.session_state.step = "start"
if "want_images" not in st.session_state:
    st.session_state.want_images = "Nie"
if "num_images" not in st.session_state:
    st.session_state.num_images = 0
if "style" not in st.session_state:
    st.session_state.style = None
if "images_urls" not in st.session_state:
    st.session_state.images_urls = []



# --- Opcje ilustracji ---
st.sidebar.markdown("---")
st.sidebar.header("🎨 Ilustracje")

want_images = st.sidebar.radio("Czy chcesz dodać ilustracje?", ["Nie", "Tak"])
st.session_state.want_images = want_images

if want_images == "Tak":
    num_images = st.sidebar.slider("📸 Ile ilustracji chcesz?", 1, 7, 3)
    style = st.sidebar.selectbox(
        "🎨 Styl ilustracji",
        ["Bajkowy", "Pastelowy", "Realistyczny", "Komiks", "Kolorowanka"]
    )
    st.session_state.num_images = num_images
    st.session_state.style = style
else:
    st.session_state.num_images = 0
    st.session_state.style = None    



# --- Cennik ---
PRICES = {
    "gpt-4o-mini": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
    "gpt-4o": {"input": 5.00 / 1_000_000, "output": 15.00 / 1_000_000},
}
IMAGE_PRICE = 0.04  # USD za obraz
USD_TO_PLN = 4.4  # przybliżony kurs przeliczeniowy

# --- Obliczanie kosztu ---
price_in = PRICES[model]["input"] * target_tokens
price_out = PRICES[model]["output"] * target_tokens
text_price = price_in + price_out

image_cost = st.session_state.num_images * IMAGE_PRICE if st.session_state.num_images else 0
total_price_usd = text_price + image_cost
total_price_pln = total_price_usd * USD_TO_PLN

# --- Wyświetlenie kosztu w sidebarze ---
st.sidebar.markdown(
    f"💰 **Szacowany koszt (tekst + ilustracje):** ~{total_price_pln:.2f} zł *(≈ {total_price_usd:.3f} USD)*"
)
st.sidebar.caption(f"📘 Kurs przybliżony: 1 USD ≈ {USD_TO_PLN} PLN")





# --- Generowanie planu opowiadania ---
if st.sidebar.button("🚀 Generuj plan opowiadania"):
    with st.spinner("✍️ Tworzę plan wydarzeń..."):

        # Ustal liczbę scen na podstawie długości historii
        scene_count = 5 if "Krótka" in length_option else 7 if "Średnia" in length_option else 9

        # Przygotuj prompt dla GPT
        prompt = f"""
        Stwórz plan opowiadania w stylu {genre.lower()}.
        Użyj {clean_language} języka i narracji.
        Plan ma się składać dokładnie z {scene_count} punktów (SCENA 1–{scene_count}),
        każdy punkt ma zawierać maksymalnie 3 zdania opisujące kluczowe wydarzenia.

        Dane kontekstowe:
        - Opis głównego bohatera: {hero_identity if hero_identity else "brak"}
        - Postacie poboczne: {side_characters if side_characters else "brak"}
        - Liczba postaci pobocznych: {side_count}
        - Miejsce akcji: {place_option}
        - Gatunek: {genre}

        {"Każda scena powinna przedstawiać moment, który można łatwo zobrazować ilustracją." if want_images == "Tak" else ""}
        
        Format odpowiedzi:
        SCENA 1: ...
        SCENA 2: ...
        SCENA 3: ...
        itd. aż do SCENA {scene_count}.
        """

        # Wywołanie modelu GPT
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.8
        )

        # Zapisz plan do stanu aplikacji
        st.session_state.plan = response.choices[0].message["content"]
        st.session_state.step = "plan"
        st.session_state.scene_images = {}




# --- Wyświetlanie planu z możliwością tworzenia ilustracji ---
if st.session_state.step == "plan" and st.session_state.plan:
    st.markdown("## 📘 Plan opowiadania")
    st.caption("Wybierz sceny i generuj ilustracje. Możesz stworzyć maksymalnie tyle ilustracji, ile ustawiłaś w panelu bocznym.")
    st.divider()

    # --- Rozbij plan na sceny ---
    scenes = [line.strip() for line in st.session_state.plan.split("\n") if line.strip()]

    # --- Licznik ilustracji ---
    total_images = st.session_state.num_images
    current_images = len(st.session_state.scene_images)
    st.progress(current_images / total_images if total_images > 0 else 0)
    st.caption(f"Ilustracje: {current_images}/{total_images}")



    # --- Iteracja po scenach ---
    for idx, scene in enumerate(scenes, start=1):
        clean_scene = scene.replace('###', '').replace('"', '')
        st.markdown(f"**{idx}. {clean_scene}**")

        col1, col2 = st.columns([0.25, 0.75])
        with col1:
            if idx in st.session_state.scene_images:
                # --- Przycisk regeneracji ilustracji ---
                if st.button(f"🔁 Wygeneruj ponownie ({idx})", key=f"regen_{idx}"):
                    with st.spinner("⏳ Generuję ponownie ilustrację..."):
                        base_prompt = STYLE_PROMPTS.get(st.session_state.style, "")
                        clean_scene = scene.replace('SCENA', '').replace(':', '').strip()

                        prompt = f"""
                        Ilustracja książkowa do sceny opowiadania.
                        Opis sceny: {clean_scene}.
                        {base_prompt}
                        Unikaj przemocy, walki, broni, smoków lub ran — pokazuj emocje, przygodę i ruch w sposób symboliczny.
                        Wysoka jakość, spójny styl, bez liter, bez tekstu, bez ramek.
                        """

                        response = openai.Image.create(
                            prompt=prompt,
                            n=1,
                            size="1024x1024"
                        )
                        image_url = response["data"][0]["url"]
                        st.session_state.scene_images[idx] = image_url
                        st.rerun()
            else:
                # --- Przycisk generowania ilustracji ---
                if len(st.session_state.scene_images) < st.session_state.num_images:
                    if st.button(f"🎨 Generuj ilustrację ({idx})", key=f"gen_{idx}"):
                        with st.spinner("🎨 Tworzę ilustrację..."):
                            style_info = STYLE_PROMPTS.get(st.session_state.style, "")
                            prompt = f"""
                            Ilustracja do sceny z opowiadania.
                            Opis sceny: {clean_scene}.
                            Styl graficzny: {st.session_state.style.lower()} – {style_info}.
                            Wysoka jakość, {st.session_state.style.lower()} klimat ilustracyjny.
                            Bez tekstu, bez podpisów, bez ramek.
                            """
                            response = openai.Image.create(
                                prompt=prompt,
                                n=1,
                                size="1024x1024"
                            )
                            image_url = response["data"][0]["url"]
                            st.session_state.scene_images[idx] = image_url
                            st.rerun()
                else:
                    st.info("✅ Osiągnięto maksymalną liczbę ilustracji ustawioną w panelu bocznym.")

        # --- Wyświetlenie obrazka ---
        with col2:
            if idx in st.session_state.scene_images:
                st.image(
                    st.session_state.scene_images[idx],
                    caption=f"Ilustracja {idx} – {st.session_state.style}",
                    use_column_width=True
                )

        st.divider()


    # --- Przyciski pod planem ---
    colA, colB = st.columns(2)
    with colA:
        if st.button("✔️ Akceptuję plan – przejdź dalej"):
            if st.session_state.plan:
                st.session_state.step = "options"
                st.success("✅ Plan zaakceptowany! Możesz przejść do tworzenia historii.")
                st.rerun()
            else:
                st.warning("⚠️ Najpierw wygeneruj plan opowiadania.")
    with colB:
        if st.button("🔄 Wygeneruj nowy plan"):
            st.session_state.plan = None
            st.session_state.scene_images = {}
            st.session_state.step = "start"
            st.rerun()





# --- Generuj ostateczną książkę ---
if st.session_state.step == "options":
    st.markdown("🎉 Wszystko gotowe! Teraz możesz wygenerować swoją historię.")
    st.caption("AI stworzy pełne opowiadanie na podstawie planu, z uwzględnieniem wybranego stylu narracji i gatunku.")
    
    if st.button("🚀 Generuj ostateczną książkę"):
        with st.spinner("⏳ Generuję opowiadanie..."):

            story_prompt = f"""
            Napisz opowiadanie (~{target_words} słów) na podstawie poniższego planu:
            {st.session_state.plan}

            Podziel historię na rozdziały odpowiadające scenom (np. Rozdział 1: ..., Rozdział 2: ...).
            Użyj {clean_language} języka narracji.

            Gatunek: {genre}.
            Główny bohater: {hero_identity if hero_identity else "brak opisu"}.
            Postacie poboczne: {side_characters if side_characters else "brak"}.
            Miejsce akcji: {place_option}.

            Zadbaj o spójność z planem wydarzeń i emocjonalne zakończenie historii.
            """

            response = openai.ChatCompletion.create(
                model=model,
                messages=[{"role": "user", "content": story_prompt}],
                max_tokens=target_tokens,
                temperature=0.8
            )

            st.session_state.story = response.choices[0].message["content"]
            st.session_state.step = "final"
            st.success("✅ Opowiadanie wygenerowane! Przejdź niżej, aby je zobaczyć.")




# --- Wyświetlenie gotowej książki ---
if st.session_state.step == "final":
    st.subheader("📚 Pełne opowiadanie")
    st.write(st.session_state.story)

    # Jeśli użytkownik stworzył ilustracje – pokaż je
    if hasattr(st.session_state, "scene_images") and st.session_state.scene_images:
        st.markdown("## 🎨 Ilustracje")
        for idx, url in st.session_state.scene_images.items():
            st.image(url, caption=f"Ilustracja {idx}", use_column_width=True)



      # --- Eksport do PDF ---
    if st.button("📥 Pobierz jako PDF"):
        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter

        # Rejestracja czcionek obsługujących polskie znaki
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.lib.utils import ImageReader

        pdfmetrics.registerFont(TTFont("DejaVuSans", "DejaVuSans.ttf"))
        pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", "DejaVuSans-Bold.ttf"))

        pdf.setFont("DejaVuSans-Bold", 16)
        pdf.drawString(50, height - 50, "📚 Fabryka Opowiadań")
        pdf.setFont("DejaVuSans", 12)
        y = height - 80

        # --- Sceny i ilustracje ---
        scenes = [line.strip() for line in st.session_state.plan.split("\n") if line.strip()]
        story_lines = st.session_state.story.split("\n")

        for idx, scene in enumerate(scenes, start=1):
            pdf.setFont("DejaVuSans-Bold", 14)
            pdf.drawString(50, y, f"SCENA {idx}")
            y -= 20

            pdf.setFont("DejaVuSans", 12)
            scene_text = "\n".join(story_lines)
            for line in [scene_text[i:i+90] for i in range(0, len(scene_text), 90)]:
                pdf.drawString(50, y, line)
                y -= 15
                if y < 150:
                    pdf.showPage()
                    pdf.setFont("DejaVuSans", 12)
                    y = height - 50

            # Ilustracja
            if idx in st.session_state.scene_images:
                try:
                    img_data = requests.get(st.session_state.scene_images[idx], stream=True).content
                    img = Image.open(io.BytesIO(img_data))
                    img.thumbnail((700, 700))
                    img_reader = ImageReader(io.BytesIO(img_data))
                    aspect = img.height / img.width
                    img_width = 450
                    img_height = img_width * aspect

                    if y - img_height < 100:
                        pdf.showPage()
                        y = height - 100

                    pdf.drawImage(img_reader, 50, y - img_height, width=img_width, height=img_height)
                    y -= img_height + 40
                except Exception as e:
                    st.warning(f"⚠️ Nie udało się dodać ilustracji {idx}: {e}")

        pdf.save()
        buffer.seek(0)

        st.download_button(
            label="📥 Kliknij tutaj, aby pobrać PDF",
            data=buffer,
            file_name="fabryka_opowiadan.pdf",
            mime="application/pdf"
        )
