import os, re
import glob

# All files in temp_email
files = glob.glob(r'd:\Web Development\LMS\payroll-system\backend\temp_email\*.py')

for f in files:
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # 1. Remove all common emojis used in the codebase
    patterns = ['😊', '📧', '🚨', '✅', '🎉', '🔔', '❌', '✨', '🚀', '🏁', '👋', '📝', '💼', '📋', '📅', '⏱️', '👤', '💬', '🏠', '🏷️', '📢', '⚡']
    for p in patterns:
        content = content.replace(p + ' ', '')
        content = content.replace(p, '')
    
    # 2. Fix the hero section background gradient
    content = re.sub(r'background:\s*linear-gradient[^;]+;', '', content)
    
    # 3. Remove the giant emoji div from hero section
    content = re.sub(r'<div style=\"font-size:\s*\d+px;.*?>.*?</div>', '', content, flags=re.DOTALL)

    with open(f, 'w', encoding='utf-8') as file:
        file.write(content)
    print(f'Processed {os.path.basename(f)}')
