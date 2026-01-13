import os
import sys
import tempfile
from flask import Flask, render_template, request, send_file
from dd1750_core import generate_dd1750_from_pdf

app = Flask(__name__)
app.secret_key = 'dd1750-secret-key'

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    print("DEBUG: /generate called")
    
    if 'bom_file' not in request.files:
        print("DEBUG: No BOM PDF uploaded")
        return render_template('index.html', error='No BOM PDF uploaded')
    
    if 'template_file' not in request.files:
        print("DEBUG: No DD1750 Template PDF uploaded")
        return render_template('index.html', error='No DD1750 Template PDF uploaded')
    
    bom_file = request.files['bom_file']
    template_file = request.files['template_file']
    
    if bom_file.filename == '' or template_file.filename == '':
        print("DEBUG: Both files must be selected")
        return render_template('index.html', error='Both files must be selected')
    
    if not (bom_file.filename.lower().endswith('.pdf') and template_file.filename.lower().endswith('.pdf')):
        print("DEBUG: Both files must be PDF format")
        return render_template('index.html', error='Both files must be PDF format')
    
    start_page = int(request.form.get('start_page', 0))
    
    print(f"DEBUG: Processing BOM: {bom_file.filename}, Template: {template_file.filename}, Start Page: {start_page}")
    
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            bom_path = os.path.join(tmpdir, 'bom.pdf')
            tpl_path = os.path.join(tmpdir, 'template.pdf')
            out_path = os.path.join(tmpdir, 'DD1750.pdf')
            
            print(f"DEBUG: Saving BOM to {bom_path}")
            bom_file.save(bom_path)
            
            print(f"DEBUG: Saving Template to {tpl_path}")
            template_file.save(tpl_path)
            
            print(f"DEBUG: Output path: {out_path}")
            sys.stdout.flush()
            
            out_path, count = generate_dd1750_from_pdf(
                bom_path=bom_path,
                template_path=tpl_path,
                out_path=out_path,
                start_page=start_page
            )
            
            print(f"DEBUG: Generation complete. Items: {count}")
            sys.stdout.flush()
            
            if not os.path.exists(out_path):
                print(f"ERROR: Output file does not exist at {out_path}")
                return render_template('index.html', error='Internal error: PDF could not be generated')
            
            file_size = os.path.getsize(out_path)
            print(f"DEBUG: Output file size: {file_size} bytes")
            sys.stdout.flush()
            
            if count == 0:
                print("DEBUG: Count is 0. Rendering error page.")
                return render_template('index.html', error='No items found in BOM')
            
            print("DEBUG: Sending file to user...")
            sys.stdout.flush()
            
            return send_file(out_path, as_attachment=True, download_name='DD1750.pdf')
    
    except Exception as e:
        print(f"CRITICAL ERROR in /generate: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return render_template('index.html', error=f"Error: {str(e)}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
