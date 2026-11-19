# Thai Meal Calorie Analyzer (IT232)

## Run
    pip install -r requirements.txt
    export GEMINI_API_KEY=your_key      # Windows: set GEMINI_API_KEY=your_key
    streamlit run app.py

## Files
- app.py          Streamlit web app (upload/camera -> analyze -> edit -> diary -> next-meal advice)
- analyzer.py     Pipeline: prompt + few-shot + DB grounding (the "customization")
- nutrition_db.csv  Starter Thai food table. VALUES ARE APPROXIMATE PLACEHOLDERS:
                  replace with the official Thai Food Composition Database (INMU / Dept. of Health)
- evaluate.py     Baseline vs Customized metrics on your own test set (test_set/labels.csv)

## Deploy (Streamlit Cloud)
Push to GitHub, create the app on share.streamlit.io, add GEMINI_API_KEY under Settings > Secrets:
    GEMINI_API_KEY = "your_key"
