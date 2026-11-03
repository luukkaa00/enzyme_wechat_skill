#!/usr/bin/env python3
"""Validate article structure and render escaped text into inline-style HTML."""
import argparse
import base64
import html
import json
import re
import shutil
from pathlib import Path
from urllib.parse import quote, unquote


def rich(text):
    return ''.join('<strong>' + html.escape(p[2:-2]) + '</strong>'
                   if p.startswith('**') and p.endswith('**') else html.escape(p)
                   for p in re.split(r'(\*\*[^*]+\*\*)', text))


def require_text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(name + ' must be non-empty text')
    return value


ARTICLE_SECTIONS = {
    'research': ('背景介绍', '研究内容', '未来展望'),
    'review': ('综述背景', '核心观点与策略', '挑战与展望'),
}


def article_sections(data):
    # Existing research drafts remain valid without an explicit article_type.
    article_type = data.get('article_type', 'research')
    if not isinstance(article_type, str) or article_type not in ARTICLE_SECTIONS:
        raise ValueError('article_type must be research or review')
    return ARTICLE_SECTIONS[article_type]


STYLE_ALIASES = {
    '1': 'academic', '01': 'academic', '翡翠': 'academic', '学术标签': 'academic', '翡翠·学术标签': 'academic',
    '2': 'molecular', '02': 'molecular', '靛蓝': 'molecular', '分子节点': 'molecular', '靛蓝·分子节点': 'molecular',
    '3': 'botanical', '03': 'botanical', '鼠尾草': 'botanical', '自然手记': 'botanical', '鼠尾草·自然手记': 'botanical',
}


def choose_style(value):
    if value is None:
        return 'academic'
    if not isinstance(value, str):
        raise ValueError('style must be a style name or string number')
    key = STYLE_ALIASES.get(value.strip(), value.strip())
    if key not in ('academic', 'molecular', 'botanical'):
        raise ValueError('style must be academic, molecular, botanical, 1, 2 or 3')
    return key


def render_figure(figure, theme, base_dir, image_export_dir=None):
    if not isinstance(figure, dict):
        raise ValueError('each image must be an object')
    path = Path(require_text(figure.get('path'), 'image path'))
    if not path.is_absolute():
        path = base_dir / path
    raw = path.read_bytes()
    if raw.startswith(b'\x89PNG\r\n\x1a\n'):
        mime = 'image/png'
    elif raw.startswith(b'\xff\xd8\xff'):
        mime = 'image/jpeg'
    elif raw.startswith(b'RIFF') and raw[8:12] == b'WEBP':
        mime = 'image/webp'
    else:
        raise ValueError('figure must be a PNG, JPEG or WebP image')
    caption = require_text(figure.get('caption'), 'image caption')
    if image_export_dir is None:
        uri = 'data:' + mime + ';base64,' + base64.b64encode(raw).decode('ascii')
    else:
        export_dir, filename, href_dir = image_export_dir
        export_dir.mkdir(parents=True, exist_ok=True)
        target = export_dir / (filename + {'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp'}[mime])
        if path.resolve() != target.resolve():
            shutil.copyfile(path, target)
        uri = quote(href_dir + '/' + target.name, safe='/')
    return ('<figure style="margin:22px 0 26px;padding:0;background:#ffffff;">'
            + '<img src="' + uri + '" alt="' + html.escape(caption, quote=True) + '" style="display:block;width:100%;height:auto;margin:0;">'
            + '<figcaption style="margin:12px 2px 0;color:#616b64;font-size:12px;line-height:1.8;text-align:center;text-indent:0;">'
            + html.escape(caption) + '</figcaption></figure>')


def render(data, base_dir=None, *, mode='preview', image_export_dir=None):
    if mode not in ('preview', 'wechat'):
        raise ValueError('mode must be preview or wechat')
    base_dir = Path(base_dir) if base_dir is not None else Path.cwd()
    assets = Path(__file__).resolve().parent.parent / 'assets'
    style_key = choose_style(data.get('style'))
    theme = json.loads((assets / 'styles.json').read_text(encoding='utf-8'))[style_key]
    title = require_text(data.get('title'), 'title')
    if not re.fullmatch(r'[^|\n]+\|[^：\n]+：[^\n]+', title):
        raise ValueError('title must follow 期刊简称|作者团队名：主题总结')
    show_subtitles = data.get('show_subtitles', False)
    if type(show_subtitles) is not bool:
        raise ValueError('show_subtitles must be true or false')
    sections = data.get('sections')
    if not isinstance(sections, list) or len(sections) != 3:
        raise ValueError('exactly three sections are required')
    blocks, text, image_number = [], [], 0
    heading_template = (assets / theme['heading_asset']).read_text(encoding='utf-8')
    for number, (section, label) in enumerate(zip(sections, article_sections(data)), 1):
        heading = require_text(section.get('heading'), 'heading')
        if heading != label and not heading.startswith(label + '｜'):
            raise ValueError('section heading must begin with ' + label + '｜')
        subtitle = heading.split('｜', 1)[1] if show_subtitles and '｜' in heading else ''
        heading_values = {'NUMBER': str(number), 'NUMBER_PAD': f'{number:02d}', 'LABEL': html.escape(label),
                          'LABEL_SIZE': f'{min(23, 120 / len(label)):.1f}',
                          'SUBTITLE': ('<p style="margin:12px 0 0;color:' + theme['main'] + ';font-size:15px;line-height:1.7;text-align:center;">' + html.escape(subtitle) + '</p>') if subtitle else ''}
        if mode == 'wechat':
            heading_html = '<h2 style="box-sizing:border-box;display:block;max-width:100%;margin:0;padding:12px 16px;border-radius:10px;background:' + theme['main'] + ';color:#ffffff;font-size:20px;line-height:1.6;text-align:center;">' + html.escape(label) + '</h2>'
        else:
            heading_html = '<h2 style="margin:0;font-size:0;line-height:0;font-weight:700;">' + re.sub(r'\{\{(NUMBER|NUMBER_PAD|LABEL|LABEL_SIZE)\}\}', lambda m: heading_values[m[1]], heading_template) + '</h2>'
        blocks.append('<section style="margin:28px 0 18px;text-align:center;">' + heading_html + heading_values['SUBTITLE'] + '</section>')
        paragraphs = section.get('paragraphs')
        if not isinstance(paragraphs, list) or not paragraphs:
            raise ValueError('each section needs paragraphs')
        subheadings = section.get('subheadings', [])
        if not isinstance(subheadings, list):
            raise ValueError('subheadings must be a list')
        if subheadings and (data.get('article_type', 'research') != 'review' or number != 2):
            raise ValueError('subheadings are supported only in the review middle section')
        if subheadings and not 2 <= len(subheadings) <= 4:
            raise ValueError('provide 2 to 4 review subheadings')
        placed_subheadings = {}
        for subheading in subheadings:
            if not isinstance(subheading, dict):
                raise ValueError('each subheading must be an object')
            position = subheading.get('before_paragraph')
            if type(position) is not int or not 1 <= position <= len(paragraphs):
                raise ValueError('before_paragraph must be an integer between 1 and paragraph count')
            if position in placed_subheadings:
                raise ValueError('subheadings cannot share the same paragraph')
            placed_subheadings[position] = require_text(subheading.get('title'), 'subheading title')
        if subheadings and 1 not in placed_subheadings:
            raise ValueError('the first review subheading must precede paragraph 1')
        if section.get('image_placeholder'):
            raise ValueError('image_placeholder is no longer supported; extract real paper figures and use images')
        figures = section.get('images', [])
        if not isinstance(figures, list):
            raise ValueError('images must be a list')
        placed_figures = {}
        for figure in figures:
            if not isinstance(figure, dict):
                raise ValueError('each image must be an object')
            position = figure.get('after_paragraph', len(paragraphs))
            if type(position) is not int or not 0 <= position <= len(paragraphs):
                raise ValueError('after_paragraph must be an integer between 0 and paragraph count')
            image_number += 1
            export = None
            if mode == 'wechat' and image_export_dir is not None:
                export = (Path(image_export_dir), f'figure_{image_number:02d}', Path(image_export_dir).name)
            placed_figures.setdefault(position, []).append(render_figure(figure, theme, base_dir, export))
        frame_open = False
        blocks.extend(placed_figures.get(0, []))
        for paragraph_number, paragraph in enumerate(paragraphs, 1):
            if not frame_open:
                blocks.append('<section data-section-body="' + str(number) + '" style="box-sizing:border-box;margin:0 0 26px;padding:20px 18px;border:1px solid ' + theme['border'] + ';border-radius:12px;background:#ffffff;">')
                frame_open = True
            if paragraph_number in placed_subheadings:
                blocks.append('<h3 style="box-sizing:border-box;margin:24px 0 12px;padding:9px 12px;border-radius:8px;background:' + theme['pale'] + ';color:' + theme['dark'] + ';font-size:17px;line-height:1.7;font-weight:700;">' + html.escape(placed_subheadings[paragraph_number]) + '</h3>')
            paragraph = require_text(paragraph, 'paragraph')
            text.append(paragraph.replace('**', ''))
            blocks.append('<p style="box-sizing:border-box;margin:0 0 14px;padding:0;color:#3d3d3d;font-size:16px;line-height:1.8;text-indent:2em;">' + rich(paragraph) + '</p>')
            if paragraph_number in placed_figures:
                blocks.append('</section>')
                frame_open = False
                blocks.extend(placed_figures[paragraph_number])
        if frame_open:
            blocks.append('</section>')
    reference = html.escape(require_text(data.get('reference'), 'reference'))
    doi = data.get('doi', '')
    if doi:
        if not isinstance(doi, str) or not re.fullmatch(r'10\.\d{4,9}/\S+', doi):
            raise ValueError('doi must be a bare DOI beginning with 10.')
        reference += '<br>DOI：<a style="color:' + theme['main'] + ';" href="https://doi.org/' + quote(doi, safe='/') + '">' + html.escape(doi) + '</a>'
    template = (Path(__file__).resolve().parent.parent / 'assets/article-template.html').read_text(encoding='utf-8')
    values = {'TITLE': html.escape(title), 'BODY': '\n'.join(blocks), 'REFERENCE': reference, 'DARK': theme['dark'], 'BORDER': theme['border']}
    result = re.sub(r'\{\{(TITLE|BODY|REFERENCE|DARK|BORDER)\}\}', lambda m: values[m[1]], template)
    tokens = re.findall(r'[\u3400-\u9fff]|[A-Za-z0-9]+(?:[._/–−-][A-Za-z0-9]+)*', ''.join(text))
    return result, len(tokens)


def suggested_filename(data):
    title = require_text(data.get('title'), 'title')
    title_parts = re.fullmatch(r'([^|\n]+)\|([^：\n]+)：[^\n]+', title)
    if not title_parts:
        raise ValueError('title must follow 期刊简称|通讯作者团队名：主题总结')
    journal = data.get('journal_abbreviation', title_parts[1])
    team = data.get('corresponding_author_team', title_parts[2])
    year = data.get('publication_year')
    if type(year) not in (str, int) or not re.fullmatch(r'(?:19|20|21)\d{2}', str(year)):
        raise ValueError('provide the verified four-digit publication_year for automatic naming')

    def component(value, label):
        value = require_text(value, label)
        value = re.sub(r'[\s\x00-\x1f<>:"/\\|?*]+', '', value).strip('.')
        if not value:
            raise ValueError(label + ' has no usable filename characters')
        return value

    return component(journal, 'journal_abbreviation') + '_' + component(team, 'corresponding_author_team') + '_' + str(year) + '.html'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument('--output', type=Path, help='explicit user-requested filename')
    output_group.add_argument('--output-dir', type=Path, help='directory for automatically named HTML')
    parser.add_argument('--style', help='academic, molecular, botanical, or style number 1/2/3')
    parser.add_argument('--preview-only', action='store_true', help='omit the companion WeChat HTML and exported figures')
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding='utf-8'))
    if args.style is not None:
        data['style'] = args.style
    result, count = render(data, args.input.resolve().parent)
    output = args.output if args.output is not None else (args.output_dir or args.input.resolve().parent) / suggested_filename(data)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result, encoding='utf-8')
    report = {'output': str(output.resolve()), 'body_count': count, 'style': choose_style(data.get('style')),
                      'count_rule': 'Chinese characters + Latin/numeric tokens; body only',
                      'within_default_target': 900 <= count <= 1100}
    if not args.preview_only:
        image_dir = output.parent / (output.stem + '_images')
        wechat_output = output.with_name(output.stem + '_公众号.html')
        wechat_html, wechat_count = render(data, args.input.resolve().parent, mode='wechat', image_export_dir=image_dir)
        assert wechat_count == count
        wechat_output.write_text(wechat_html, encoding='utf-8')
        image_files = [str((output.parent / unquote(src)).resolve())
                       for src in re.findall(r'<img src="([^"]+)"', wechat_html)]
        report.update(wechat_output=str(wechat_output.resolve()),
                      image_directory=str(image_dir.resolve()) if image_files else None,
                      image_files=image_files)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
