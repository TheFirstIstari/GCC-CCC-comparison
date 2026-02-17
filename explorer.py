import os
import subprocess
import tempfile
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

# --- CONFIGURATION ---
# Get the directory where this script lives
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Path to Claude's Compiler (Sibling directory)
CCC_BINARY = os.path.join(BASE_DIR, "claudes-c-compiler/target/release/ccc")

# Path to GCC (System installed)
GCC_BINARY = "/usr/bin/gcc"

# Use RAM for temporary files (Fastest option, 0 disk wear)
TEMP_DIR = "/dev/shm"

# --- HTML TEMPLATE ---
HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>CCC Performance Studio</title>
    <style>
        :root { --bg: #1e1e1e; --panel: #252526; --text: #d4d4d4; --accent: #0e639c; --border: #3e3e42; }
        body { margin: 0; background: var(--bg); color: var(--text); font-family: 'Segoe UI', sans-serif; height: 100vh; display: flex; flex-direction: column; overflow: hidden; }
        
        header { background: #333; padding: 10px 20px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--border); }
        h1 { margin: 0; font-size: 1.1rem; color: #fff; }
        
        .toolbar { display: flex; gap: 15px; align-items: center; }
        select { background: #3c3c3c; color: white; border: 1px solid #555; padding: 5px; border-radius: 3px; font-family: sans-serif; }
        
        button { background: var(--accent); color: white; border: none; padding: 6px 14px; cursor: pointer; font-size: 13px; font-weight: 600; border-radius: 2px; }
        button:hover { background: #1177bb; }
        button:disabled { background: #4d4d4d; cursor: not-allowed; }

        #container { display: flex; flex: 1; height: 100%; }
        .panel { flex: 1; display: flex; flex-direction: column; border-right: 1px solid var(--border); min-width: 0; }
        .panel:last-child { border: none; }
        
        .header { background: var(--panel); padding: 8px 15px; font-size: 0.85rem; font-weight: bold; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
        .stats { font-size: 0.75rem; color: #888; font-weight: normal; }
        
        textarea, .output { flex: 1; background: var(--bg); color: #dcdcdc; border: none; resize: none; padding: 15px; font-family: 'Consolas', 'Monaco', monospace; font-size: 13px; line-height: 1.5; outline: none; white-space: pre; overflow: auto; }
        
        .asm-arm { color: #9cdcfe; }
        .asm-x86 { color: #ce9178; }
        .error { color: #f48771; background: #2d1b1b; }
    </style>
</head>
<body>
    <header>
        <h1>CCC-GCC Studio <span style="opacity:0.5; font-size:0.8em; margin-left:10px;"></span></h1>
        <div class="toolbar">
            <select id="opt-level">
                <option value="-O0">O0 (None)</option>
                <option value="-O1">O1 (Basic)</option>
                <option value="-O2" selected>O2 (Standard)</option>
                <option value="-O3">O3 (Aggressive)</option>
                <option value="-Os">Os (Size)</option>
            </select>
            <button id="compileBtn" onclick="compile()">Compile (Ctrl+Enter)</button>
        </div>
    </header>

    <div id="container">
        <!-- Source Code -->
        <div class="panel" style="flex: 1.2;">
            <div class="header">C Source</div>
            <textarea id="source" spellcheck="false">
int square(int num) {
    return num * num;
}

int main() {
    return square(10);
}</textarea>
        </div>

        <!-- GCC Output -->
        <div class="panel">
            <div class="header">
                GCC (ARM64)
                <span id="gcc-stats" class="stats"></span>
            </div>
            <div id="gcc-out" class="output asm-arm"></div>
        </div>

        <!-- CCC Output -->
        <div class="panel">
            <div class="header">
                CCC (x86_64)
                <span id="ccc-stats" class="stats"></span>
            </div>
            <div id="ccc-out" class="output asm-x86"></div>
        </div>
    </div>

    <script>
        const sourceBox = document.getElementById('source');
        
        // Shortcut: Ctrl+Enter to compile
        sourceBox.addEventListener('keydown', e => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') compile();
        });

        async function compile() {
            const btn = document.getElementById('compileBtn');
            const opt = document.getElementById('opt-level').value;
            const gcc = document.getElementById('gcc-out');
            const ccc = document.getElementById('ccc-out');
            
            // UI Reset
            btn.disabled = true;
            btn.innerText = "Processing...";
            gcc.innerText = "...";
            ccc.innerText = "...";
            gcc.className = 'output';
            ccc.className = 'output';
            document.getElementById('gcc-stats').innerText = '';
            document.getElementById('ccc-stats').innerText = '';

            try {
                const res = await fetch('/compile', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ 
                        code: sourceBox.value,
                        opt: opt
                    })
                });
                
                const data = await res.json();
                
                // --- Render GCC ---
                if (data.gcc.success) {
                    gcc.innerText = data.gcc.asm;
                    gcc.classList.add('asm-arm');
                    document.getElementById('gcc-stats').innerText = opt;
                } else {
                    gcc.innerText = data.gcc.error;
                    gcc.classList.add('error');
                }

                // --- Render CCC ---
                if (data.ccc.success) {
                    ccc.innerText = data.ccc.asm;
                    ccc.classList.add('asm-x86');
                    document.getElementById('ccc-stats').innerText = "(Default)";
                } else {
                    ccc.innerText = data.ccc.error;
                    ccc.classList.add('error');
                }

            } catch (e) {
                alert("Error: " + e);
            }
            
            btn.disabled = false;
            btn.innerText = "Compile (Ctrl+Enter)";
        }
    </script>
</body>
</html>
"""

# --- FLASK APP ---
@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/compile', methods=['POST'])
def compile_code():
    data = request.json
    code = data.get('code', '')
    opt_level = data.get('opt', '-O0') # Get optimization level (default -O0)

    if not code.strip():
        return jsonify({"gcc": {"success": False, "error": "No code"}, "ccc": {"success": False, "error": "No code"}})

    print(f"--> Compiling with level: {opt_level}")

    # Create temp directory in RAM (/dev/shm)
    with tempfile.TemporaryDirectory(dir=TEMP_DIR) as temp_dir:
        src = os.path.join(temp_dir, "test.c")
        with open(src, "w") as f:
            f.write(code)

        results = {}

        # ---------------------------------------------------------
        # 1. GCC (ARM64)
        # ---------------------------------------------------------
        try:
            # Command: gcc -O2 -S -fverbose-asm -o - test.c
            cmd = [GCC_BINARY, opt_level, "-S", "-fverbose-asm", "-o", "-", src]
            
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            
            if proc.returncode == 0:
                results["gcc"] = {"success": True, "asm": proc.stdout}
            else:
                results["gcc"] = {"success": False, "error": proc.stderr}
        except Exception as e:
            results["gcc"] = {"success": False, "error": str(e)}

        # ---------------------------------------------------------
        # 2. CCC (x86_64)
        # ---------------------------------------------------------
        try:
            out_bin = os.path.join(temp_dir, "ccc_out")
            
            # Note: We do NOT pass 'opt_level' to CCC yet because we don't know
            # if it supports optimization flags. It might crash if we do.
            cmd = [CCC_BINARY, "-c", src, "-o", out_bin]
            
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5, cwd=temp_dir)
            
            if proc.returncode != 0:
                # Compilation Failed
                err = proc.stderr if proc.stderr else proc.stdout
                results["ccc"] = {"success": False, "error": err or "Unknown CCC Error"}
            else:
                # Compilation Succeeded -> Disassemble
                if os.path.exists(out_bin):
                    # Try using specific cross-objdump first, fall back to generic
                    objdump_cmd = "objdump"
                    # Check if the specific one exists (better for x86 on ARM)
                    try:
                        subprocess.run(["x86_64-linux-gnu-objdump", "--version"], capture_output=True)
                        objdump_cmd = "x86_64-linux-gnu-objdump"
                    except:
                        pass # Fallback to system objdump
                    
                    dis = subprocess.run(
                        [
                            objdump_cmd, 
                            "-d", 
                            "-M", "intel", 
                            "--no-show-raw-insn", # Hide hex bytes
                            out_bin
                        ],
                        capture_output=True, text=True, timeout=5
                    )
                    
                    if dis.returncode == 0:
                        # Clean up headers to show just assembly
                        lines = dis.stdout.splitlines()
                        clean_lines = []
                        start_printing = False
                        
                        for line in lines:
                            if "Disassembly of section" in line:
                                start_printing = True
                                continue
                            
                            if start_printing and line.strip():
                                # Try to strip addresses like "   1a:"
                                parts = line.split('\t', 1)
                                if len(parts) > 1:
                                    clean_lines.append("\t" + parts[1])
                                else:
                                    clean_lines.append(line)

                        results["ccc"] = {"success": True, "asm": "\n".join(clean_lines)}
                    else:
                        results["ccc"] = {"success": False, "error": f"Objdump failed: {dis.stderr}"}
                else:
                    results["ccc"] = {"success": False, "error": "Binary missing"}

        except Exception as e:
            results["ccc"] = {"success": False, "error": str(e)}

        return jsonify(results)

if __name__ == '__main__':
    # Listen on all interfaces so you can access it from your desktop
    app.run(host='0.0.0.0', port=5000, debug=True)