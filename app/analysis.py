"""审查分析：冲突图构建、容器分组、传递冲突链、最小冲突批次集合。"""

from collections import deque

from .rules import (
    LEVEL_LABELS,
    LEVELS,
    categories_of,
    find_pair_conflicts,
    find_self_conflicts,
    CATEGORY_LABELS,
)

MAX_EXACT_COVER_EDGES = 120  # 冲突边超过该数量时退化为贪心近似
MAX_TRANSITIVE_CHAINS = 60   # 传递冲突链最多输出条数


def _batch_view(batch):
    cats = sorted(categories_of(batch))
    return {
        "id": batch["id"],
        "name": batch["name"],
        "volume": batch["volume"],
        "ph": batch["ph"],
        "oxidizing": bool(batch["oxidizing"]),
        "volatile": bool(batch["volatile"]),
        "tags": batch.get("tags") or [],
        "categories": cats,
        "category_labels": [CATEGORY_LABELS.get(c, c) for c in cats],
    }


def build_conflicts(batches):
    """两两冲突列表 + 自反应风险列表。"""
    conflicts = []
    for i in range(len(batches)):
        for j in range(i + 1, len(batches)):
            for rule in find_pair_conflicts(batches[i], batches[j]):
                conflicts.append({
                    "a": batches[i]["id"], "b": batches[j]["id"],
                    "a_name": batches[i]["name"], "b_name": batches[j]["name"],
                    "rule_id": rule["id"], "hazard": rule["hazard"],
                    "level": rule["level"], "level_label": LEVEL_LABELS[rule["level"]],
                    "desc": rule["desc"],
                })
    self_reactive = []
    for b in batches:
        for rule in find_self_conflicts(b):
            self_reactive.append({
                "batch_id": b["id"], "name": b["name"],
                "rule_id": rule["id"], "hazard": rule["hazard"],
                "level": rule["level"], "level_label": LEVEL_LABELS[rule["level"]],
                "desc": rule["desc"],
            })
    conflicts.sort(key=lambda c: -LEVELS[c["level"]])
    self_reactive.sort(key=lambda c: -LEVELS[c["level"]])
    return conflicts, self_reactive


def _adjacency(batches, conflicts):
    adj = {b["id"]: set() for b in batches}
    for c in conflicts:
        adj[c["a"]].add(c["b"])
        adj[c["b"]].add(c["a"])
    return adj


def assign_containers(batches, conflicts):
    """贪心图着色：按冲突度降序，把批次放入首个无冲突容器。"""
    adj = _adjacency(batches, conflicts)
    order = sorted(batches, key=lambda b: (-len(adj[b["id"]]), b["id"]))
    containers = []          # list[list[batch_id]]
    assignment = {}          # batch_id -> container index
    for b in order:
        bid = b["id"]
        for idx, members in enumerate(containers):
            if all(m not in adj[bid] for m in members):
                members.append(bid)
                assignment[bid] = idx
                break
        else:
            containers.append([bid])
            assignment[bid] = len(containers) - 1
    return containers, assignment


def find_transitive_chains(batches, conflicts):
    """传递冲突：同一连通分量内无直接冲突、但经中间批次间接关联的批次对。

    输出每对的最短冲突路径（A→B→C…），按路径长度升序。
    """
    adj = _adjacency(batches, conflicts)
    names = {b["id"]: b["name"] for b in batches}
    direct = {frozenset((c["a"], c["b"])) for c in conflicts}

    reported = set()
    chains = []
    for start in adj:
        # 以 start 为源 BFS，得到到各节点的最短路径父指针
        parent = {start: None}
        q = deque([start])
        while q:
            u = q.popleft()
            for v in adj[u]:
                if v not in parent:
                    parent[v] = u
                    q.append(v)
        for other in parent:
            if other == start:
                continue
            key = frozenset((start, other))
            if key in direct or key in reported:
                continue
            path = [other]
            while path[-1] != start:
                path.append(parent[path[-1]])
            path.reverse()
            chains.append({
                "path": path,
                "names": [names[x] for x in path],
                "hops": len(path) - 1,
            })
            reported.add(key)
    chains.sort(key=lambda c: (c["hops"], c["path"]))
    return chains[:MAX_TRANSITIVE_CHAINS]


def minimal_conflict_batches(batches, conflicts):
    """最小冲突批次集合（最小点覆盖）：移除这些批次后，剩余批次两两兼容。

    边数较少时用分支限界求精确解，否则退化为贪心近似。
    """
    edges = list({tuple(sorted((c["a"], c["b"]))) for c in conflicts})
    names = {b["id"]: b["name"] for b in batches}
    if not edges:
        return {"ids": [], "names": [], "exact": True}

    def greedy(edge_list):
        cover = []
        remaining = list(edge_list)
        while remaining:
            degree = {}
            for u, v in remaining:
                degree[u] = degree.get(u, 0) + 1
                degree[v] = degree.get(v, 0) + 1
            pick = max(degree, key=lambda x: (degree[x], -x))
            cover.append(pick)
            remaining = [e for e in remaining if pick not in e]
        return cover

    if len(edges) > MAX_EXACT_COVER_EDGES:
        cover = greedy(edges)
        return {"ids": cover, "names": [names[i] for i in cover], "exact": False}

    best = {"cover": greedy(edges)}  # 贪心解作为上界

    def branch(edge_list, cover):
        if len(cover) >= len(best["cover"]):
            return
        if not edge_list:
            best["cover"] = list(cover)
            return
        # 下界：极大匹配数
        matched, matching = set(), 0
        for u, v in edge_list:
            if u not in matched and v not in matched:
                matched.add(u)
                matched.add(v)
                matching += 1
        if len(cover) + matching >= len(best["cover"]):
            return
        # 选度最大的边的一个端点分支
        degree = {}
        for u, v in edge_list:
            degree[u] = degree.get(u, 0) + 1
            degree[v] = degree.get(v, 0) + 1
        u, v = max(edge_list, key=lambda e: degree[e[0]] + degree[e[1]])
        branch([e for e in edge_list if u not in e], cover + [u])
        branch([e for e in edge_list if v not in e], cover + [v])

    branch(edges, [])
    cover = sorted(best["cover"])
    return {"ids": cover, "names": [names[i] for i in cover], "exact": True}


def run_review(batches):
    """完整审查：返回汇总、容器分组、冲突、传递链、最小冲突批次。"""
    conflicts, self_reactive = build_conflicts(batches)
    containers_idx, assignment = assign_containers(batches, conflicts)
    by_id = {b["id"]: b for b in batches}

    adj = _adjacency(batches, conflicts)
    containers = []
    for idx, member_ids in enumerate(containers_idx):
        members = [_batch_view(by_id[bid]) for bid in member_ids]
        containers.append({
            "index": idx + 1,
            "name": f"容器 {chr(65 + idx) if idx < 26 else idx + 1}",
            "members": members,
            "total_volume": round(sum(m["volume"] for m in members), 3),
            "member_count": len(members),
        })

    transitive = find_transitive_chains(batches, conflicts)
    minimal = minimal_conflict_batches(batches, conflicts)

    degree = sorted(
        ({"id": b["id"], "name": b["name"], "conflict_count": len(adj[b["id"]])}
         for b in batches),
        key=lambda x: (-x["conflict_count"], x["id"]),
    )

    max_level = "low"
    for c in conflicts + self_reactive:
        if LEVELS[c["level"]] > LEVELS[max_level]:
            max_level = c["level"]

    return {
        "summary": {
            "batch_count": len(batches),
            "conflict_count": len(conflicts),
            "self_reactive_count": len(self_reactive),
            "container_count": len(containers),
            "transitive_count": len(transitive),
            "max_level": max_level,
            "max_level_label": LEVEL_LABELS[max_level],
            "safe": not conflicts and not self_reactive,
        },
        "containers": containers,
        "conflicts": conflicts,
        "self_reactive": self_reactive,
        "transitive": transitive,
        "minimal_removal": minimal,
        "conflict_degree": degree,
    }
