"""从 GitHub 官方 API 获取公开 PR，生成可嵌入个人主页的明暗两套 SVG。

仅使用标准库。GITHUB_TOKEN 只从环境读取，不落盘，不输出请求头。
搜索结果不完整、分页超限或接口失败时停止，保留上一次完整统计。
"""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import escape
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
TZ = timezone(timedelta(hours=8))


def api(path, token):
    """只请求 GitHub 官方 API；异常不回显鉴权信息。"""
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'public-pr-profile',
               'X-GitHub-Api-Version': '2022-11-28'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    request = urllib.request.Request('https://api.github.com' + path, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'GitHub API HTTP {exc.code}；未更新统计。') from None


def fetch(username, token):
    """搜索本人已合并公开 PR，再读取合并时间与仓库公开状态，私密信息不写产物。"""
    if not re.fullmatch(r'[A-Za-z0-9-]{1,39}', username):
        raise ValueError('GitHub 用户名无效。')
    api('/users/' + username, token)
    query = urllib.parse.urlencode({'q': f'is:pr is:merged is:public author:{username}',
                                   'sort': 'created', 'order': 'asc', 'per_page': 100})
    items = []
    page = 1
    while True:
        result = api('/search/issues?' + query + f'&page={page}', token)
        if result.get('incomplete_results') or result['total_count'] > 1000:
            raise RuntimeError('搜索不完整或超过1000条；需分时间窗口查询，保留旧结果。')
        items.extend(result['items'])
        if len(items) >= result['total_count']:
            break
        if not result['items']:
            raise RuntimeError('分页结果缺失，保留旧结果。')
        page += 1
    repositories, prs = {}, []
    for item in items:
        repo = item['repository_url'].removeprefix('https://api.github.com/repos/')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
            raise ValueError('仓库路径无效。')
        if repo not in repositories:
            info = api('/repos/' + repo, token)
            if info['private']:
                raise RuntimeError('检测到非公开仓库，拒绝生成公开统计。')
            repositories[repo] = {'name': repo, 'stars': info['stargazers_count']}
        pr = api(f'/repos/{repo}/pulls/{int(item["number"])}', token)
        if not pr.get('merged_at') or pr['user']['login'].casefold() != username.casefold():
            raise RuntimeError('搜索与PR详情不一致，保留旧结果。')
        prs.append({'repository': repo, 'number': pr['number'], 'merged_at': pr['merged_at']})
    if len({(p['repository'], p['number']) for p in prs}) != len(prs):
        raise RuntimeError('分页出现重复项，保留旧结果。')
    return {'username': username, 'updated_at': datetime.now(TZ).isoformat(timespec='seconds'),
            'scope': 'authored merged public pull requests', 'pull_requests': prs,
            'repositories': list(repositories.values())}


def summarize(data):
    """按合并日期汇总，明确区分自己仓库与外部仓库；零记录是有效结果。"""
    now = datetime.fromisoformat(data['updated_at']).astimezone(TZ)
    today = now.date()
    prs = data['pull_requests']
    days = Counter(datetime.fromisoformat(p['merged_at'].replace('Z', '+00:00')).astimezone(TZ).date() for p in prs)
    start = today - timedelta(days=29)
    counts = Counter(p['repository'] for p in prs)
    repos = sorted(data['repositories'], key=lambda r: (-counts[r['name']], r['name'].casefold()))
    return {'total': len(prs), 'external': sum(p['repository'].split('/')[0].casefold() != data['username'].casefold() for p in prs),
            'recent': sum(n for day, n in days.items() if start <= day <= today),
            'days': days, 'repos': repos, 'counts': counts, 'today': today, 'now': now}


def render(data, dark=False):
    """生成无脚本、无外部字体的 SVG，适配 GitHub 图片代理与浅色/暗色主题。"""
    s = summarize(data)
    bg, text, muted, line, accent, tint = ('#101D1C', '#D6F6E8', '#9CBFB0', '#33594D', '#74DCAD', '#182F27') if dark else ('#EDF5F0', '#183F34', '#4D7161', '#AEC8BC', '#206B51', '#DFEBE3')
    repos = s['repos'][:8]
    height = 590 + max(1, len(repos)) * 68
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="1000" height="{height}" viewBox="0 0 1000 {height}" role="img" aria-labelledby="title desc">',
             f'<title id="title">{escape(data["username"])} · 公开PR贡献</title>',
             f'<desc id="desc">已合并{s["total"]}个公开PR，其中{s["external"]}个向他人仓库提交，近30天合并{s["recent"]}个。</desc>',
             f'<rect width="1000" height="{height}" fill="{bg}"/>',
             f'<style>text{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;fill:{text}}}.muted{{fill:{muted}}}.accent{{fill:{accent}}}.mono{{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}}</style>']
    def label(x, y, value, size=16, cls='', **attrs):
        attributes = ' '.join(f'{k.replace("_", "-")}="{v}"' for k, v in attrs.items())
        parts.append(f'<text x="{x}" y="{y}" font-size="{size}" class="{cls}" {attributes}>{escape(str(value))}</text>')
    def rule(y):
        parts.append(f'<path d="M48 {y}H952" stroke="{line}"/>')
    label(48, 50, '■  OPEN SOURCE / CONTRIBUTIONS', 12, 'accent mono', letter_spacing='2')
    label(48, 110, data['username'], 38, font_weight='650')
    label(48, 148, '每一次贡献，都有迹可循。', 17, 'muted')
    label(952, 50, 'GITHUB / PR ACTIVITY', 11, 'muted mono', text_anchor='end')
    rule(182)
    label(48, 225, 'MERGED PULL REQUESTS', 12, 'accent mono', letter_spacing='2')
    label(48, 309, s['total'], 72, font_weight='650')
    label(48, 342, '个公开 PR 已合并', 17)
    label(420, 279, s['external'], 38, font_weight='600')
    label(420, 311, '提交给他人仓库', 14, 'muted')
    label(740, 279, f'+{s["recent"]}', 38, 'accent', font_weight='600')
    label(740, 311, '近 30 天合并', 14, 'muted')
    # 每列对应一天，每点一个PR；同日超过六个时用数字标出，避免挤出图表。
    start = s['today'] - timedelta(days=89)
    parts.append(f'<path d="M48 432H952" stroke="{line}"/>')
    for i in range(90):
        day = start + timedelta(days=i)
        count = s['days'][day]
        x = 54 + i * 892 / 89
        for j in range(min(count, 6)):
            parts.append(f'<circle cx="{x:.1f}" cy="{422-j*12}" r="3.5" fill="{accent}"><title>{day.isoformat()} · {count} PR</title></circle>')
        if count > 6:
            label(f'{x:.1f}', 341, count, 10, 'accent mono', text_anchor='middle')
    if not any(start <= d <= s['today'] for d in s['days']):
        label(48, 397, '近 90 天暂无公开 PR 合并记录', 14, 'muted')
    label(48, 458, start.strftime('%m-%d'), 11, 'muted mono')
    label(952, 458, s['today'].strftime('%m-%d'), 11, 'muted mono', text_anchor='end')
    label(500, 458, '近 90 天 · 按合并日期', 11, 'muted', text_anchor='middle')
    rule(485)
    label(48, 520, 'REPOSITORIES', 12, 'accent mono', letter_spacing='2')
    label(952, 520, 'MERGED PR / STARS', 11, 'muted mono', text_anchor='end')
    for i, repo in enumerate(repos):
        y = 565 + i * 68
        name = repo['name']
        parts.append(f'<a xlink:href="https://github.com/{escape(name, quote=True)}">')
        parts.append(f'<rect x="48" y="{y-24}" width="32" height="32" rx="8" fill="{tint}"/>')
        label(64, y-3, f'{i+1:02}', 12, 'accent mono', text_anchor='middle')
        label(98, y, name if len(name) <= 47 else name[:44]+'…', 17, 'mono', font_weight='550')
        label(788, y, f'{s["counts"][name]} PR', 15, 'mono', text_anchor='end')
        stars = str(repo['stars']) if repo['stars'] < 1000 else f'{repo["stars"]/1000:.1f}k'
        label(952, y, f'☆ {stars}', 14, 'muted mono', text_anchor='end')
        parts.append('</a>')
        rule(y+27)
    if not repos:
        label(48, 570, '暂无已合并的公开 PR；未来的贡献会自动显示在这里。', 15, 'muted')
    if len(s['repos']) > len(repos):
        label(48, height-56, f'另有 {len(s["repos"])-len(repos)} 个仓库，完整记录见 GitHub。', 12, 'muted')
    label(48, height-20, 'GitHub REST API · 仅公开数据 · 每日更新', 11, 'muted')
    label(952, height-20, s['now'].strftime('%Y-%m-%d %H:%M')+' UTC+8', 11, 'muted mono', text_anchor='end')
    parts.append('</svg>')
    return '\n'.join(parts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--username', default='Dengzi555')
    args = parser.parse_args()
    data = fetch(args.username, os.environ.get('GITHUB_TOKEN', ''))
    # 全部 API 成功、两套 SVG 均生成后才替换文件；失败不把旧统计误写成零。
    outputs = {ROOT/'stats.json': json.dumps(data, ensure_ascii=False, indent=2)+'\n',
               ROOT/'assets/pr-stats.svg': render(data), ROOT/'assets/pr-stats-dark.svg': render(data, True)}
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix+'.tmp')
        temporary.write_text(content, encoding='utf-8')
        temporary.replace(path)
    result = summarize(data)
    print(f'已更新公开 PR：合并 {result["total"]}，外部贡献 {result["external"]}，近30天 {result["recent"]}。')


if __name__ == '__main__':
    main()
