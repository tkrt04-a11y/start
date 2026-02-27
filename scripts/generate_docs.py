"""Simple script to regenerate HTML docs from markdown sources."""
import os
import markdown

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
README = os.path.join(BASE, 'README.md')
OUTPUT = os.path.join(BASE, 'docs', 'index.html')

HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Driven Development Starter Kit</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; margin: 2rem; line-height: 1.6; }}
        h1,h2,h3 {{ color: #333; }}
        pre {{ background: #f5f5f5; padding: 1rem; overflow-x: auto; }}
        code {{ background: #f5f5f5; padding: 0.2rem 0.4rem; }}
    </style>
</head>
<body>
{content}
</body>
</html>'''


def main():
    with open(README, 'r', encoding='utf-8') as f:
        md = f.read()
    html_body = markdown.markdown(md, extensions=['fenced_code', 'tables'])
    full = HTML_TEMPLATE.format(content=html_body)
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        f.write(full)
    print(f"Generated {OUTPUT}")


if __name__ == '__main__':
    main()
