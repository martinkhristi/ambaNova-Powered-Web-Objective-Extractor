import streamlit as st
import os
import json
import re
import time
from firecrawl import FirecrawlApp
from openai import OpenAI

# Set Streamlit page config
st.set_page_config(
    page_title="SambaNova Powered Web Objective Extractor", 
    layout="wide",
    initial_sidebar_state="expanded",
    page_icon="🌐"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #1E88E5;
        margin-bottom: 1rem;
    }
    .sambanova {
        color: #FF8C00;
        font-weight: bold;
    }
    .subheader {
        font-size: 1.5rem;
        color: #424242;
        margin-bottom: 2rem;
    }
    .card {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .success-box {
        background-color: #d4edda;
        color: #155724;
        padding: 15px;
        border-radius: 5px;
        margin-bottom: 20px;
    }
    .info-box {
        background-color: #cce5ff;
        color: #004085;
        padding: 15px;
        border-radius: 5px;
        margin-bottom: 20px;
    }
    .stButton>button {
        background-color: #1E88E5;
        color: white;
        font-weight: bold;
        padding: 10px 15px;
        border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)

# Sidebar for API keys and configuration
with st.sidebar:
    st.image("https://via.placeholder.com/150x80?text=SambaNova+Extractor", width=200)
    st.markdown("### ⚙️ Configuration")

    with st.expander("API Settings", expanded=True):
        firecrawl_api_key = st.text_input("🔑 Firecrawl API Key", type="password")
        sambanova_api_key = st.text_input("🔐 SambaNova API Key", type="password")
        selected_model = st.selectbox(
            "🧠 Choose SambaNova Model",
            [
                "Llama-4-Maverick-17B-128E-Instruct",
                "Llama-4-Scout-17B-16E-Instruct"
            ],
            index=1
        )

    with st.expander("ℹ️ Help"):
        st.markdown("""
        **How to use:**
        1. Enter your API keys
        2. Input the website URL
        3. Clearly state your objective
        4. Click "Start Crawling"
        
        **Tips for good objectives:**
        - Be specific about what you're looking for
        - Examples: "Find contact email", "Get product pricing", "Find company address"
        """)

    st.markdown("---")
    st.markdown('Powered by Deepseek V3 and <span class="sambanova">SambaNova</span>', unsafe_allow_html=True)

st.markdown('<h1 class="main-header">🌐 <span class="sambanova">SambaNova</span> Powered Web Objective Extractor</h1>', unsafe_allow_html=True)
st.markdown('<p class="subheader">Extract specific information from websites using AI</p>', unsafe_allow_html=True)

col1, col2 = st.columns([3, 2])

with col1:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    url = st.text_input("🌍 Website URL to Crawl", placeholder="https://example.com")
    objective = st.text_area("🎯 What is your objective?", 
                            placeholder="e.g., 'Find contact email', 'Get product pricing', 'List main services'",
                            height=120)
    st.markdown('</div>', unsafe_allow_html=True)

with col2:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("### Options")

    max_pages = st.slider("📁 Maximum pages to scan", min_value=1, max_value=10, value=3)

    advanced_options = st.expander("Advanced Options")
    with advanced_options:
        temperature = st.slider("🌡️ AI Temperature", min_value=0.0, max_value=1.0, value=0.1, step=0.1)
        st.caption("Lower = more consistent, Higher = more creative")

    start_button = st.button("🚀 Start Crawling", use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

if "results" not in st.session_state:
    st.session_state.results = None
    st.session_state.crawling_complete = False
    st.session_state.progress = 0
    st.session_state.current_url = ""
    st.session_state.logs = []

def find_relevant_page_via_map(objective, url, app, client, model):
    try:
        st.session_state.logs.append(f"🔍 Generating search parameter for: {objective}")

        map_prompt = f"""
        The map function generates a list of URLs from a website and it accepts a search parameter. 
        Based on the objective of: {objective}, come up with a 1-2 word search parameter that will help us find the information we need. 
        Only respond with 1-2 words nothing else.
        """

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": map_prompt}],
            temperature=temperature,
            top_p=0.1
        )
        search_term = response.choices[0].message.content.strip().split()[0]
        st.session_state.logs.append(f"🌤️ Using search term: '{search_term}'")

        st.session_state.logs.append(f"🗺️ Mapping website structure: {url}")
        map_website = app.map_url(url, params={"search": search_term})
        links = map_website.get("urls", []) or map_website.get("links", [])

        if links:
            st.session_state.logs.append(f"✅ Found {len(links)} potential pages")
        else:
            st.session_state.logs.append("❌ No relevant pages found")

        return links
    except Exception as e:
        st.session_state.logs.append(f"❌ Error during site mapping: {str(e)}")
        return []

def find_objective_in_pages(pages, objective, app, client, model, max_pages):
    st.session_state.logs.append(f"🔎 Beginning search across {min(len(pages), max_pages)} pages")

    for i, link in enumerate(pages[:max_pages]):
        st.session_state.current_url = link
        st.session_state.progress = (i / min(len(pages), max_pages)) * 100
        st.session_state.logs.append(f"📄 Scraping page {i+1}/{min(len(pages), max_pages)}: {link}")

        try:
            scraped = app.scrape_url(link, params={"formats": ["markdown"]})

            prompt = f"""
            Given the following scraped content and objective, determine if the objective is met.
            If it is, extract the relevant information in a simple JSON format. 
            If the objective is not met, respond with exactly 'Objective not met'.

            JSON format:
            {{
                "found": true,
                "data": {{
                    // extracted information here
                }}
            }}

            Objective: {objective}
            Scraped content: {scraped['markdown'][:10000]}
            """

            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Only respond in raw JSON or exactly 'Objective not met'. Do NOT include commentary or <think> tags."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                top_p=0.1
            )

            raw_output = response.choices[0].message.content.strip()
            raw_output = re.sub(r"<think>.*?</think>", "", raw_output, flags=re.DOTALL).strip()

            if raw_output.lower() == "objective not met":
                st.session_state.logs.append("ℹ️ Objective not found on this page")
                continue

            if raw_output.startswith("```"):
                raw_output = raw_output.strip("```")
                if raw_output.startswith("json"):
                    raw_output = raw_output[4:].strip()

            parsed = json.loads(raw_output)
            if parsed.get("found"):
                st.session_state.logs.append("🎉 Objective found!")
                return parsed["data"]
        except Exception as e:
            error_msg = f"⚠️ Error processing page: {str(e)}"
            st.session_state.logs.append(error_msg)
            continue
    return None

if start_button and all([firecrawl_api_key, sambanova_api_key, url, objective]):
    st.session_state.results = None
    st.session_state.crawling_complete = False
    st.session_state.progress = 0
    st.session_state.logs = []

    progress_bar = st.progress(0)
    status_container = st.empty()
    log_container = st.expander("View Logs", expanded=True)

    try:
        app = FirecrawlApp(api_key=firecrawl_api_key)
        client = OpenAI(
            base_url="https://api.sambanova.ai/v1",
            api_key=sambanova_api_key
        )

        status_container.info("🔍 Mapping website and identifying relevant pages...")
        pages = find_relevant_page_via_map(objective, url, app, client, selected_model)

        with log_container:
            st.write("\n".join(st.session_state.logs))

        if not pages:
            status_container.error("❌ No relevant pages found.")
        else:
            status_container.info("🔎 Scanning pages for requested information...")
            result = find_objective_in_pages(pages, objective, app, client, selected_model, max_pages)

            while not st.session_state.crawling_complete:
                progress_bar.progress(int(st.session_state.progress))
                with log_container:
                    st.write("\n".join(st.session_state.logs))

                if st.session_state.progress >= 100 or result is not None:
                    st.session_state.crawling_complete = True
                    break
                time.sleep(0.1)

            if result:
                st.session_state.results = result
                status_container.success("✅ Objective fulfilled!")
                progress_bar.progress(100)
            else:
                status_container.error("❌ Could not fulfill the objective on scanned pages.")
                progress_bar.progress(100)
    except Exception as e:
        status_container.error(f"❌ An error occurred: {str(e)}")
        st.session_state.logs.append(f"🛑 Fatal error: {str(e)}")
        with log_container:
            st.write("\n".join(st.session_state.logs))

if st.session_state.results:
    st.markdown("---")
    st.markdown("## 📊 Results")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("### 📝 Extracted Information")
        st.json(st.session_state.results)
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("### 📌 Summary")

        data_points = len(st.session_state.results.keys()) if isinstance(st.session_state.results, dict) else 1

        st.markdown(f"""
        - 🎯 **Objective**: {objective}
        - 🌐 **Website**: {url}
        - 📊 **Data points extracted**: {data_points}
        - ⏱️ **Pages scanned**: {len(st.session_state.logs)}
        """)

        col_a, col_b = st.columns(2)
        with col_a:
            st.download_button(
                "📅 Download JSON",
                data=json.dumps(st.session_state.results, indent=2),
                file_name="extracted_data.json",
                mime="application/json"
            )
        with col_b:
            if isinstance(st.session_state.results, dict):
                csv_data = "\n".join([f"{k},{v}" for k, v in st.session_state.results.items()])
                st.download_button(
                    "📅 Download CSV",
                    data=csv_data,
                    file_name="extracted_data.csv",
                    mime="text/csv"
                )
        st.markdown('</div>', unsafe_allow_html=True)
elif not all([firecrawl_api_key, sambanova_api_key, url, objective]) and start_button:
    st.warning("⚠️ Please fill in all required fields.")

st.markdown("---")
st.markdown('Web Objective Extractor v2.0 | Powered by Llama 4  and <span class="sambanova">SambaNova</span> AI', unsafe_allow_html=True)
