# Script para limpiar views.py
import re

with open('engine/views.py', 'rb') as f:
    content = f.read()

# Encontrar el final de status=500) y eliminar todo hasta @login_required
pattern = b'status=500\)'
match = re.search(pattern, content)
if match:
    end_pos = match.end()
    # Buscar el siguiente @login_required
    remaining = content[end_pos:]
    func_start = remaining.find(b'@login_required')
    if func_start > 0:
        # Mantener hasta status=500) y luego desde @login_required
        clean = content[:end_pos] + b'\n\n' + remaining[func_start:]
        with open('engine/views.py', 'wb') as out:
            out.write(clean)
        print('Fixed!')
    else:
        print('@login_required not found')
else:
    print('Pattern not found')

