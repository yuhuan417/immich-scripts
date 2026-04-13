#!/usr/bin/env python3

import argparse
import itertools
import random
from pathlib import Path


EN_SUBJECTS = [
    "a cat", "a dog", "a red car", "a blue bicycle", "a child", "an old man", "a young woman",
    "a chef", "a teacher", "a runner", "a singer", "a guitarist", "a fisherman", "a pilot",
    "a train", "an airplane", "a boat", "a robot", "a book", "a cup of coffee", "a bowl of noodles",
    "a pizza", "a hamburger", "a laptop", "a camera", "a smartphone", "a mountain", "a waterfall",
    "a beach", "a forest", "a desert", "a snow field", "a city street", "a bridge", "a temple",
    "a museum", "a library", "a stadium", "a flower garden", "a panda", "a horse", "an astronaut",
]
EN_ACTIONS = [
    "sleeping", "running", "jumping", "reading", "cooking", "dancing", "singing", "painting",
    "riding", "driving", "walking", "smiling", "working", "studying", "swimming", "climbing",
    "looking at the camera", "talking on the phone", "drinking tea", "playing football",
]
EN_CONTEXTS = [
    "at sunset", "in the rain", "under bright sunlight", "at night", "in a studio", "on the street",
    "in the snow", "in a classroom", "in a kitchen", "at the seaside", "in a crowded market",
    "inside a train station", "on a mountain trail", "in front of a white wall", "with colorful lights",
]
EN_STYLES = [
    "photo", "close-up photo", "wide shot", "documentary photo", "cinematic frame", "poster design",
    "oil painting", "watercolor illustration", "3d render", "anime style image", "black and white photo",
]

ZH_SUBJECTS = [
    "一只猫", "一只狗", "一辆红色汽车", "一辆蓝色自行车", "一个小孩", "一位老人", "一位年轻女性",
    "一名厨师", "一名老师", "一名跑步者", "一名歌手", "一位吉他手", "一名渔民", "一名飞行员",
    "一列火车", "一架飞机", "一艘小船", "一个机器人", "一本书", "一杯咖啡", "一碗面条",
    "一个披萨", "一个汉堡", "一台笔记本电脑", "一台相机", "一部手机", "一座高山", "一处瀑布",
    "一片海滩", "一片森林", "一片沙漠", "一片雪地", "一条城市街道", "一座桥", "一座寺庙",
    "一座博物馆", "一座图书馆", "一个体育场", "一片花园", "一只熊猫", "一匹马", "一名宇航员",
]
ZH_ACTIONS = [
    "在睡觉", "在奔跑", "在跳跃", "在读书", "在做饭", "在跳舞", "在唱歌", "在绘画",
    "在骑行", "在驾驶", "在散步", "在微笑", "在工作", "在学习", "在游泳", "在攀爬",
    "正在看向镜头", "正在打电话", "正在喝茶", "正在踢足球",
]
ZH_CONTEXTS = [
    "在日落时分", "在雨中", "在强烈阳光下", "在夜晚", "在摄影棚里", "在街头", "在雪地里",
    "在教室里", "在厨房里", "在海边", "在热闹的市场里", "在火车站内", "在山路上",
    "在白墙前", "在彩色灯光下",
]
ZH_STYLES = [
    "照片", "特写照片", "广角画面", "纪实照片", "电影感画面", "海报设计", "油画", "水彩插画",
    "3D渲染图", "动漫风格图片", "黑白照片",
]

SEARCH_PREFIXES = [
    "find images of", "search for", "show me", "looking for", "need a picture of",
    "搜索", "查找", "帮我找", "我想看", "给我来一张",
]
QUESTIONS = [
    "what does {subject} look like {context}",
    "how would you describe {subject} {action} {context}",
    "哪里能看到{subject}{action}{context}",
    "{subject}{action}{context}是什么样子",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a deterministic set of diverse multilingual search queries.")
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", type=int, default=20260413)
    return parser.parse_args()


def build_english_queries() -> list[str]:
    queries = []
    for style, subject, action, context in itertools.product(EN_STYLES, EN_SUBJECTS, EN_ACTIONS, EN_CONTEXTS):
        queries.append(f"{style} of {subject} {action} {context}")
        queries.append(f"{subject} {action} {context}, {style}")
        queries.append(f"find images of {subject} {action} {context}")
    return queries


def build_chinese_queries() -> list[str]:
    queries = []
    for style, subject, action, context in itertools.product(ZH_STYLES, ZH_SUBJECTS, ZH_ACTIONS, ZH_CONTEXTS):
        queries.append(f"{context}{action}的{subject}{style}")
        queries.append(f"{subject}{action}{context}，{style}")
        queries.append(f"搜索：{context}{action}的{subject}")
    return queries


def build_mixed_queries() -> list[str]:
    queries = []
    for prefix, subject, context in itertools.product(SEARCH_PREFIXES, EN_SUBJECTS[:20] + ZH_SUBJECTS[:20], EN_CONTEXTS[:8] + ZH_CONTEXTS[:8]):
        queries.append(f"{prefix} {subject} {context}")
    for template in QUESTIONS:
        for subject in EN_SUBJECTS[:20]:
            for action in EN_ACTIONS[:10]:
                for context in EN_CONTEXTS[:8]:
                    queries.append(template.format(subject=subject, action=action, context=context))
        for subject in ZH_SUBJECTS[:20]:
            for action in ZH_ACTIONS[:10]:
                for context in ZH_CONTEXTS[:8]:
                    queries.append(template.format(subject=subject, action=action, context=context))
    return queries


def main() -> int:
    args = parse_args()
    rng = random.Random(args.seed)
    candidates = build_english_queries() + build_chinese_queries() + build_mixed_queries()
    unique = []
    seen = set()
    for query in candidates:
        text = " ".join(query.split())
        if text not in seen:
            seen.add(text)
            unique.append(text)
    rng.shuffle(unique)
    if len(unique) < args.count:
        raise RuntimeError(f"Only generated {len(unique)} unique queries, fewer than requested {args.count}")
    selected = unique[: args.count]
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(selected) + "\n", encoding="utf-8")
    print(f"count={len(selected)}")
    print(f"output={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
