"""冲突图算法：容器分组、传递冲突簇、最小冲突批次集。

把批次看作顶点、禁配冲突看作边：
- 容器分组  = 图着色（同色顶点互不相邻），贪心着色保证同容器内无冲突；
- 传递冲突簇 = 冲突图的连通分量，A-B、B-C 冲突意味着 A 与 C 经 B 传递关联；
- 最小冲突批次集 = 最小点覆盖（Minimum Vertex Cover），移除这些批次后
  剩余批次两两兼容。规模小时用分支限界精确求解，过大时退化为贪心近似。
"""

from collections import deque

# 精确求解的边数安全上限，超过则使用贪心近似，保证接口响应速度
_EXACT_EDGE_LIMIT = 400


def _build_adj(ids, edges):
    adj = {i: set() for i in ids}
    for u, v in edges:
        if u in adj and v in adj and u != v:
            adj[u].add(v)
            adj[v].add(u)
    return adj


def assign_containers(ids, edges):
    """贪心图着色分组：相互禁配的批次不会被分入同一容器。

    返回容器列表，每个容器是批次 id 列表（按度数降序着色，颜色即容器）。
    """
    adj = _build_adj(ids, edges)
    order = sorted(ids, key=lambda n: (-len(adj[n]), n))
    color = {}
    for n in order:
        used = {color[m] for m in adj[n] if m in color}
        c = 0
        while c in used:
            c += 1
        color[n] = c
    containers = {}
    for n in ids:
        containers.setdefault(color[n], []).append(n)
    return [sorted(members) for _, members in sorted(containers.items())]


def _bfs_path(adj, src, dst, allowed):
    """在 allowed 顶点集内求 src 到 dst 的一条最短路径。"""
    prev = {src: None}
    queue = deque([src])
    while queue:
        n = queue.popleft()
        if n == dst:
            break
        for m in adj[n]:
            if m in allowed and m not in prev:
                prev[m] = n
                queue.append(m)
    if dst not in prev:
        return None
    path, n = [], dst
    while n is not None:
        path.append(n)
        n = prev[n]
    return path[::-1]


def conflict_clusters(ids, edges, max_chains=10):
    """连通分量即传递冲突簇；簇内无直接冲突的批次对给出最短传递链。"""
    adj = _build_adj(ids, edges)
    seen = set()
    clusters = []
    for start in ids:
        if start in seen or not adj[start]:
            continue
        comp, stack = [], [start]
        seen.add(start)
        while stack:
            n = stack.pop()
            comp.append(n)
            for m in adj[n]:
                if m not in seen:
                    seen.add(m)
                    stack.append(m)
        comp.sort()
        comp_set = set(comp)
        chains = []
        for i, u in enumerate(comp):
            for v in comp[i + 1:]:
                if v in adj[u]:
                    continue  # 直接冲突，不属于"传递"
                path = _bfs_path(adj, u, v, comp_set)
                if path:
                    chains.append(path)
        clusters.append({
            "batch_ids": comp,
            "indirect_chains": chains[:max_chains],
        })
    return clusters


def _greedy_cover(adj):
    """贪心点覆盖：反复摘除当前度数最大的顶点。"""
    adj = {n: set(s) for n, s in adj.items()}
    cover = []
    while True:
        u = max(adj, key=lambda n: len(adj[n]))
        if not adj[u]:
            return cover
        cover.append(u)
        for m in adj[u]:
            adj[m].discard(u)
        adj[u] = set()


def minimum_conflict_set(ids, edges):
    """最小冲突批次集（最小点覆盖）：移除后全部冲突消除。"""
    if not edges:
        return []
    adj = _build_adj(ids, edges)
    best = _greedy_cover(adj)
    if len(edges) > _EXACT_EDGE_LIMIT:
        return sorted(best)

    def branch(adj, chosen):
        nonlocal best
        if len(chosen) >= len(best):
            return
        edge = None
        for u, nbrs in adj.items():
            if nbrs:
                edge = (u, next(iter(nbrs)))
                break
        if edge is None:
            best = list(chosen)
            return
        u, v = edge
        for w in (u, v):  # 边的任一端点必有一个在覆盖中
            new_adj = {n: (s - {w}) for n, s in adj.items() if n != w}
            branch(new_adj, chosen + [w])

    branch({n: set(s) for n, s in adj.items()}, [])
    return sorted(best)
