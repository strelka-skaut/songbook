import os
from pdfreader import PDFDocument
import json


from flask import Flask, render_template_string, request, jsonify

# -----------------------
# SAMPLE DATA (replace with your own)
# -----------------------
# Schema:
# {
#   "Title": {"page_count": int, "order": int}
# }

# Sort titles by existing order

app = Flask(__name__)

data = {}
sorted_titles = list() # sorted(items.keys(), key=lambda t: items[t]["order"])

# -----------------------
# HTML TEMPLATE WITH SORTABLEJS
# -----------------------
TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset=\"UTF-8\">
    <title>Manual Sorter</title>
    <script src=\"https://cdn.jsdelivr.net/npm/sortablejs@1.15.0/Sortable.min.js\"></script>
    <style>
        body { font-family: sans-serif; margin: 1rem auto; max-width: 180ch; font-size: 0.9rem; }
        #list {
            margin-top: 0.5rem;
            display: flex;
            flex-wrap: wrap;
            flex-direction: column;
            gap: 0.4rem  1rem;
            height: 80vh;
        }
        .item {
            padding: 0.4rem 0.6rem;
            border-radius: 6px;
            width: 13.5rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.9rem;
        }
        .title { font-weight: 600; transform-text: capitalize; }
        .page-chip {
            padding: 0.15rem 0.35rem;
            border-radius: 4px;
            font-size: 0.85rem;
        }
        .one-page { background: #d9f5d9; }
        .two-page { background: #fff6c7; }
        button {
            margin-top: 0.5rem;
            margin-right: 0.5rem
            padding: 0.6rem 1.2rem;
            font-size: 1rem;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            background: #4a7bd1;
            color: white;
        }
        button:hover { background: #3a66b3; }
        .order-note { font-size: 0.8rem; opacity: 0.8; margin-bottom: 0.5rem; }
    </style>
</head>
<body>
    <div id=\"list\">
        {% for title in titles %}
        <div class=\"item\" data-title=\"{{ title }}\"
             style=\"background: {{ '#d9f5d9' if data[title].page_count == 1 else ('#fff6c7' if data[title].page_count == 2 else '#f2f2f2') }};\">
            <span class=\"title\">{{ title.split(".tex")[0] }}</span>
            <span class=\"page-chip {{ 'one-page' if data[title].page_count == 1 else ('two-page' if data[title].page_count == 2 else '') }}\">
                {{ data[title].page_count }}
            </span>
        </div>
        {% endfor %}
    </div>

    <button id=\"save-btn\">Save Order</button>
    <button id=\"copy-btn\">Copy to clipboard</button>

    <script>
        const list = document.getElementById('list');
        Sortable.create(list, {
            animation: 150
        });

        document.getElementById('save-btn').onclick = function() {
            const result = Array.from(document.querySelectorAll('.item'))
                .map((el, index) => ({ title: el.dataset.title, order: index }));

            fetch('/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(result)
            }).then(r => r.json()).then(data => {
                alert('Saved!');
            });
        };
        document.getElementById('copy-btn').onclick = function() {
            const lines = Array.from(document.querySelectorAll('.item'))
                .map(el => `\\importsong{${el.dataset.title}}`);

            const text = lines.join('\\n');

            navigator.clipboard.writeText(text).then(() => {
                alert('Copied to clipboard!');
            });
        };
     </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(TEMPLATE, titles=sorted_titles, data=data)

@app.route('/save', methods=['POST'])
def save():
    global data, sorted_titles

    new_order = request.get_json()

    print(new_order)
    # Apply new order to items dict
    for entry in new_order:
        t = entry['title']
        data[t]['order'] = entry['order']

    with open('song_order.json', 'w') as output_file:
        output_file.write(json.dumps(data, ensure_ascii=False, indent=3))

    sorted_titles = sorted(data.keys(), key=lambda t: data[t]["order"])
    return render_template_string(TEMPLATE, titles=sorted_titles, data=data)

# -----------------------
# RUN SERVER (debug disabled to avoid multiprocessing issues)
# -----------------------
def order_songs():
    global data
    existing_songs = get_existing_song_list()

    with open("song_order.json") as input_file:
        data = json.loads(input_file.read())

    for existing_song in existing_songs:
        with open(f"output/{existing_song}.pdf", "rb") as song_file:
            page_count = len(list(PDFDocument(song_file).pages()))
        if existing_song not in data:
            data[existing_song] = {'page_count': page_count, 'order': len(data)}
        else:
            data[existing_song]['page_count'] = page_count

    present_to_user()

def get_existing_song_list():
    return [ name.split(".pdf")[0] for name in os.listdir("output") if name.endswith(".pdf")]

def present_to_user():
    global data, sorted_titles
    sorted_titles = sorted(data.keys(), key=lambda t: data[t]["order"])
    app.run(debug=False, use_reloader=False, port=5000)

def get_song_data(existing_songs):
    data = {}
    for index, song in enumerate(existing_songs):
        with open(f"output/{song}.pdf", "rb") as song_file:
            page_count = len(list(PDFDocument(song_file).pages()))
            print(f"{song}\t{page_count}")
            data[song] = {'page_count': page_count, 'order': index}

    with open(f"song_order.json", "w") as output_file:
        output_file.write(json.dumps(data, ensure_ascii=False, indent=3))
    return data

if __name__ == "__main__":
    order_songs()
