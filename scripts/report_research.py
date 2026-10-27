"""Verify complete experiment evidence and export a Chinese course research report.

Uses only stdlib/project tools; plotting is a separate, isolated artifact tool.
"""
import argparse
import csv
import html
import itertools
import json
import math
import statistics
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flbench.records import published_records
from flbench.repository import CONFIG, COST, MANIFEST, file_hash, find_root, load_json, protocol_hash
from flbench.research import write_json

LABELS = {"fedavg_u_uniform": "Uniform", "fedprox_u_uniform": "FedProx", "scaffold_uniform": "SCAFFOLD",
          "fedavg_u_round_robin": "Round-robin", "fedavg_u_fast_random": "Fast/Random", "fedavg_u_oort": "Oort-adapt",
          "ghj_coverage": "ghj Coverage", "ghj_coverage_no_wait": "Coverage: no wait", "ghj_coverage_no_speed": "Coverage: no speed",
          "fedavg_sample_weighted": "Sample-weighted FedAvg", "local_only": "Local-only", "centralized": "Centralized"}


def stat(values):
    values = list(values)
    return {"n": len(values), "mean": statistics.mean(values),
            "sd": statistics.stdev(values) if len(values) > 1 else 0.0}


def paired(candidate, reference):
    differences = [candidate[s] - reference[s] for s in sorted(candidate)]
    observed = abs(statistics.mean(differences))
    transformed = [abs(statistics.mean(d * sign for d, sign in zip(differences, signs)))
                   for signs in itertools.product((-1, 1), repeat=len(differences))]
    return {**stat(differences), "differences_by_seed": dict(zip(sorted(candidate), differences)),
            "exact_two_sided_sign_flip_p": sum(value >= observed - 1e-15 for value in transformed) / len(transformed)}


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
                     + ["| " + " | ".join(map(str, row)) + " |" for row in rows])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, output = find_root(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    records = published_records(root)
    selection = load_json(root / "agents/ghj/SELECTION.json")
    config, costs, manifest = load_json(root / CONFIG), load_json(root / COST), load_json(root / MANIFEST)
    core = load_json(root / "configs/final/core-final-v2.json")
    preregistration_commit = subprocess.check_output(
        ["git", "log", "--diff-filter=A", "--format=%H", "--", "configs/final/core-final-v2.json"],
        cwd=root, text=True).strip().splitlines()[-1]
    indexed = {r["run_id"]: r for r in records}
    final = []
    for index, row in enumerate(core["frozen_run_matrix"]):
        record = indexed.get(f"ghj-core-final-v2-{index + 1:03d}")
        if not record or record["status"] != "complete":
            raise ValueError("Missing/failed core row: " + str(index + 1))
        if (record["config_hash"] != core["config_hashes"][row["config"]] or record["seed"] != row["seed"]
                or record["scenario"] != row["scenario"] or record["stage"] != "test"
                or record["protocol_hash"] != core["protocol_hash"] or record["j_dev"] is not None):
            raise ValueError("Core row differs from its preregistration.")
        final.append(record)
    if len(final) != 175 or len({r["run_id"] for r in final}) != 175:
        raise ValueError("Expected 175 unique final test runs.")
    evidence, missing = [], []
    for record in records:
        archive = (root / record["artifact_uri"]).resolve()
        if not archive.is_relative_to(root) or not archive.is_file() or file_hash(archive) != record["artifact_sha256"]:
            missing.append(record["run_id"])
            continue
        summary_path = archive.parent / "summary.json"
        summary = load_json(summary_path) if summary_path.exists() else None
        evidence.append({"record": record, "summary": summary})
    if missing:
        raise ValueError("Artifact checksum failed: " + ", ".join(missing))
    summaries = {e["record"]["run_id"]: e["summary"] for e in evidence}
    groups = []
    for scenario in config["scenarios"]:
        for method in LABELS:
            current = [r for r in final if r["scenario"] == scenario and r["method_id"] == method]
            if not current:
                continue
            if sorted(r["seed"] for r in current) != config["evaluation"]["final_seeds"]:
                raise ValueError("Final group missing preregistered seed.")
            measure = {"method_id": method, "label": LABELS[method], "scenario": scenario,
                       **stat(r["mean_client_macro_f1"] for r in current),
                       "scores_by_seed": {r["seed"]: r["mean_client_macro_f1"] for r in current},
                       "run_ids": [r["run_id"] for r in current]}
            for key in ("wall_seconds", "cpu_seconds", "sim_seconds_used", "training_steps", "completed_rounds",
                        "up_bytes", "down_bytes", "tail_20_percent_macro_f1", "pooled_macro_f1"):
                measure[key] = stat(summaries[r["run_id"]][key] for r in current)
            groups.append(measure)
    primary = "natural_heterogeneous"
    main_groups = {g["method_id"]: g for g in groups if g["scenario"] == primary}
    candidate = main_groups["ghj_coverage"]
    strongest = selection["strongest_baseline"]["method_id"]
    comparison = paired(candidate["scores_by_seed"], main_groups[strongest]["scores_by_seed"])
    all_comparisons = {method: paired(candidate["scores_by_seed"], main_groups[method]["scores_by_seed"])
                       for method in (e["method_id"] for e in selection["baseline_selection"])}
    confirmation = [r for r in records if r["stage"] == "confirmation"]
    confirm_by_method = {method: {r["seed"]: r["mean_client_macro_f1"] for r in confirmation if r["method_id"] == method}
                         for method in ("ghj_coverage", strongest)}
    confirm_comparison = paired(confirm_by_method["ghj_coverage"], confirm_by_method[strongest])
    matched = []
    for method in ("fedavg_u_uniform", "fedavg_u_fast_random", "ghj_coverage"):
        runs = [r for r in records if r["run_id"].startswith("ghj-matched-100-v1-") and r["method_id"] == method]
        if len(runs) != 3 or any(r["completed_rounds"] != 100 for r in runs):
            raise ValueError("Missing matched-round diagnostic.")
        matched.append({"method_id": method, "label": LABELS[method], **stat(r["j_dev"] for r in runs),
                        "sim_seconds_used": stat(r["sim_seconds_used"] for r in runs)})
    detail = {"status": "verified", "protocol_hash": protocol_hash(root), "code_commit": core["code_commit"],
              "final_matrix_preregistration_commit": preregistration_commit,
              "core_planned": 175, "core_complete": len(final), "published_terminal_runs": len(records),
              "failed_runs": [r["run_id"] for r in records if r["status"] != "complete"],
              "artifact_checksums_verified": len(evidence), "selection": selection,
              "config": config, "costs": costs, "data_manifest_hash": manifest["content_sha256"],
              "groups": groups, "primary_preregistered_comparison": comparison,
              "all_primary_paired_comparisons": all_comparisons, "confirmation_comparison": confirm_comparison,
              "matched_100_rounds": matched, "evidence": evidence,
              "unknown_measurements": {"per_run_peak_memory_bytes": None,
                                       "reference_end_to_end_simulated_system_seconds": None,
                                       "centralized_initial_data_upload_bytes": None},
              "no_significance_claim": True}
    write_json(output / "results.json", detail)
    with (output / "results.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["run_id", "method", "scenario", "seed", "stage", "fidelity", "macro_f1", "sim_seconds", "rounds", "steps", "up_bytes", "down_bytes", "wall_seconds", "cpu_seconds"])
        for record in records:
            summary = summaries.get(record["run_id"]) or {}
            writer.writerow([record["run_id"], record["method_id"], record["scenario"], record["seed"], record["stage"],
                             record["fidelity"], record["mean_client_macro_f1"], record["sim_seconds_used"], record["completed_rounds"],
                             summary.get("training_steps"), record["up_bytes"], record["down_bytes"], record["wall_seconds"], summary.get("cpu_seconds")])
    delta = comparison["mean"]
    outcome = "提高" if delta > 0 else "降低"
    judgment = ("观察到超过预注册实际意义阈值的均值改善，但五种子不足以支持 p<0.05 的显著性主张。"
                if delta >= config["evaluation"]["minimum_meaningful_delta"] else
                "未证实候选相对最强开发基线有达到预注册阈值的优势；该负结果同样保留。")
    primary_methods = [e["method_id"] for e in selection["baseline_selection"]] + ["ghj_coverage"]
    primary_table = table(["方法", "测试 Macro-F1 均值±SD", "最差20%用户", "平均轮数", "上/下行 MiB", "实际 Wall秒"],
        [[LABELS[m], f"{main_groups[m]['mean']:.6f} ± {main_groups[m]['sd']:.6f}",
          f"{main_groups[m]['tail_20_percent_macro_f1']['mean']:.6f}", f"{main_groups[m]['completed_rounds']['mean']:.1f}",
          f"{main_groups[m]['up_bytes']['mean']/2**20:.2f} / {main_groups[m]['down_bytes']['mean']/2**20:.2f}",
          f"{main_groups[m]['wall_seconds']['mean']:.2f}"] for m in primary_methods])
    paired_table = table(["种子", "候选−预选最强基线"], [[s, f"{v:+.6f}"] for s,v in comparison["differences_by_seed"].items()])
    ablation_table = table(["主条件配置", "均值±SD"], [[LABELS[m], f"{main_groups[m]['mean']:.6f} ± {main_groups[m]['sd']:.6f}"]
        for m in ("ghj_coverage", "ghj_coverage_no_wait", "ghj_coverage_no_speed", "fedavg_sample_weighted")])
    scenario_labels = {"near_iid_homogeneous": "近IID / 同构", "near_iid_heterogeneous": "近IID / 异构",
                       "natural_homogeneous": "自然用户 / 同构", "natural_heterogeneous": "自然用户 / 异构"}
    scenario_table = table(["条件", "候选均值", "SCAFFOLD均值", "配对均值差"],
        [[scenario_labels[s], f"{c['mean']:.6f}", f"{b['mean']:.6f}", f"{c['mean']-b['mean']:+.6f}"]
         for s in config["scenarios"]
         for c in groups if c["scenario"] == s and c["method_id"] == "ghj_coverage"
         for b in groups if b["scenario"] == s and b["method_id"] == strongest])
    reference_table = table(["曝光匹配参考", "数据划分", "均值±SD"],
        [[g["label"], scenario_labels[g["scenario"]], f"{g['mean']:.6f} ± {g['sd']:.6f}"]
         for g in groups if g["method_id"] in ("local_only", "centralized")])
    matched_table = table(["开放验证诊断", "完整B均值", "100轮均值±SD", "100轮模拟秒"],
        [[item["label"], f"{selected['mean']:.6f}", f"{item['mean']:.6f} ± {item['sd']:.6f}",
          f"{item['sim_seconds_used']['mean']:.6f}"]
         for item in matched
         for selected in ([selection["candidate"]] if item["method_id"] == "ghj_coverage" else
                          [e for e in selection["baseline_selection"] if e["method_id"] == item["method_id"]])])
    sections = [
        ("摘要", f"完成了 HAPT 的数据审计、完整强基线、预算校准、144 次全预算开发运行、9 次等轮数诊断、6 次受限确认，以及 175/175 次预注册正式运行。候选相对开放验证阶段预选的最强基线 {LABELS[strongest]}，主条件测试 Macro-F1 均值{outcome} {abs(delta):.6f}。{judgment}"),
        ("1. Motivation：研究动机", "云边端设备训练速度不同，按速度选择可提高同一时间内的更新数量，却可能减少慢用户的数据参与。研究问题是在完全相同模拟时间预算下，显式等待覆盖能否提高客户端等权平均质量。本研究是轻量 CPU 仿真，不声称实现真实工业网络或证明隐私安全。"),
        ("2. Existing Gap：对照与研究边界", "速度和代表性权衡已有大量研究，不能宣称首次提出。使用 Uniform、FedProx、SCAFFOLD、轮转、Fast/Random 和 Oort 适配版作为对照。Oort 保留 RMS 效用、探索/利用、成本惩罚和 pacer，但与原实现仍有探索与时间不确定度等差异，因此结论只适用于本适配及当前协议。"),
        ("3. Observation：搜索前观察", f"先做 36 次完整 LR/轮数校准，所有数据来自开放验证。预注册选择共享 LR={config['training']['initial_learning_rate']}；B={config['evaluation']['budget_sim_seconds']:.9f} 模拟秒，约为异构 Uniform 200 轮；最小实际意义差异={config['evaluation']['minimum_meaningful_delta']:.6f}。不选择预算内最好 checkpoint，统一评价最后一个完整轮次，故相邻轮质量可能有波动。"),
        ("4. Hypothesis：可证伪假设", "在 Fast/Random 上预留等待触发的慢/陈旧用户覆盖名额，可用部分吞吐换取更好的客户端代表性。预注册名额 {1,2}、等待阈值 {.05B,.1B,.2B}；若对强基线的配对均值改善未达到阈值，则不支持具有实际意义的收益。"),
        ("5. Method：方法与公平性", f"30 个用户，每轮 6 人，先轮转预热 5 轮，每个选中客户端 4 个 SGD step，batch 16；模型 48→64→6，等客户端聚合。预热、完整序列化权重及控制变量消息、选择器与 SCAFFOLD 额外计算均按冻结系数计费。速度倍率 1/4/16，每档10人，映射独立于训练标签。候选配置为 {selection['candidate']['config']}，按预注册近似持平规则优先较少覆盖名额和较大等待阈值，并非只挑最高点估计；开放验证后冻结，确认与测试均不再调参。训练 2748、验证1194、测试1462窗口，原始采样区间零交集、标准化仅拟合训练数据。"),
        ("6. Evaluation：正式评测", "7种联邦方法×4条件×5种子=140；两种解释性参考×两种数据条件×5=20；两项候选消融×5=10；经典样本量加权 FedAvg×5=5，合计175。正式种子101..105；每个测试用户固定六类 Macro-F1，30人等权平均。Local-only每人160step、Centralized4800step，只作曝光匹配参考，不比较同B优势。参考运行的FL消息计数和FL模拟时钟为0；数据集中上传量、参考系统端到端模拟耗时未测量，明确保留null，不能解释为集中训练免费。\n\n" + primary_table + "\n\n" + paired_table),
        ("7. Analysis：机制、配对与负结果", f"主比较严格使用开发阶段预选的 {LABELS[strongest]}，没有用测试集更换对照。配对均值 {delta:+.6f}，SD={comparison['sd']:.6f}，精确双侧符号翻转 p={comparison['exact_two_sided_sign_flip_p']:.4f}。确认集平均配对差={confirm_comparison['mean']:+.6f}，未据此调整参数。其余六条基线的完整配对差见 results.json。\n\n{judgment}\n\n" + ablation_table + "\n\n等100轮诊断只用开放验证、标为partial，共9次；用于区分吞吐与相同更新数的质量。参与次数、等待和尾部质量展示描述性关联，不把相关窗口或30个用户冒充更多独立种子。"),
        ("8. Limitations：局限与适用边界", "仅一个HAPT数据源、轻量统计特征和小MLP；窗口按记录拆分但仍来自同一数据集，30人均参与训练，因此不是未见用户泛化。每个正式种子同时改变初始化、minibatch和独立于标签的速度映射，种子SD包含多种随机来源。设备倍率、网络速率、RTT是模拟假设；实测CPU中位数是固定参考系数，不能等同真实异构网络的精确时延。Oort是有限适配；每类选择器只测代表配置的固定开销，成本细微变化仍可能影响末轮。覆盖名额的同速度档消融只匹配单轮档位，后续选择轨迹可能分离。五个正式种子最小双侧符号翻转p=.0625，不能宣称p<.05。峰值内存未测量，保留null；没有执行可选235次扩展或第二独立数据集。所有实验由ghj单工作区顺序完成，不冒称其他三位成员已参与；团队人工审阅、Champion晋级及GitHub管理需实际成员权限。"),
        ("复现与证据", f"研究代码 commit：{core['code_commit']}；正式矩阵预注册commit：{preregistration_commit}；协议SHA-256：{core['protocol_hash']}；数据SHA-256：{manifest['content_sha256']}。全部{len(evidence)}个已发布终态工件zip已核验SHA-256。源代码、冻结配置、原始测量、逐轮日志和检查点均随交付提供。\n\n`uv sync --locked`\n\n`uv run --locked --exact python scripts/research.py campaign configs/final/core-final-v2.json`\n\n已发布结果不会覆盖；新机器先执行数据准备，随后同一命令按被冻结矩阵复现。详见 docs/ghj-execution.md。开发排行榜由同步脚本生成，Champion未自动晋级。"),
        ("参考资料", "[1] McMahan et al., Communication-Efficient Learning of Deep Networks from Decentralized Data, AISTATS 2017. https://proceedings.mlr.press/v54/mcmahan17a.html [2] Li et al., Federated Optimization in Heterogeneous Networks, MLSys 2020. [3] Karimireddy et al., SCAFFOLD: Stochastic Controlled Averaging for Federated Learning, ICML 2020. https://proceedings.mlr.press/v119/karimireddy20a.html [4] Lai et al., Oort, OSDI 2021. https://www.usenix.org/conference/osdi21/presentation/lai [5] UCI HAPT dataset #341. https://archive.ics.uci.edu/dataset/341/ . Oort永久源代码链接与逐项偏离说明见docs/oort-adaptation.md。")]
    sections = [(h, body.replace("其余六条基线", "六条基线")) for h, body in sections]
    sections = [(h, body + "\n\n四条件敏感性（同一预选对照）：\n\n" + scenario_table
                 + "\n\n曝光匹配参考：\n\n" + reference_table if h.startswith("6.") else body)
                for h, body in sections]
    sections = [(h, body + "\n\n" + matched_table if h.startswith("7.") else body) for h, body in sections]
    sections = [(h, body.replace("已发布结果不会覆盖；新机器先执行数据准备，随后同一命令按被冻结矩阵复现。",
                 "该命令检查/恢复原活动，已有终态会跳过。要实际重新训练175行并保留原证据，执行 "
                 "`uv run --locked --exact python scripts/replay_campaign.py --replicate-id core-final-replay-v1`。"
                 "复现沿用原种子，不增加独立样本量。完整交付包包含Git历史、处理后缓存、逐轮工件和恢复脚本；"
                 "从Git单独检出则需先准备数据和取回工件。")) for h, body in sections]
    title = "面向异构云边感知的联邦客户端选择：ghj 可复现实验报告"
    md = "# " + title + "\n\n" + "\n\n".join("## " + h + "\n\n" + body for h,body in sections)
    figure_names = [("quality-curves", "四条件质量—模拟时间曲线"), ("paired-differences", "主条件五种子配对差"),
                    ("participation", "客户端参与与尾部质量"), ("matched-updates", "同时间与同更新数对照"),
                    ("ablations", "候选覆盖机制消融"), ("scenario-sensitivity", "数据/速度异构敏感性")]
    md += "\n\n## 图表\n\n" + "\n\n".join(f"![{caption}](figures/{name}.png)" for name,caption in figure_names) + "\n"
    (output / "研究报告.md").write_text(md, encoding="utf-8")
    content = []
    for heading, body in sections:
        chunks = body.split("\n\n")
        content.append("<h2>" + html.escape(heading) + "</h2>")
        for chunk in chunks:
            if chunk.startswith("| "):
                lines = chunk.splitlines()
                cells = [[c.strip() for c in line.strip("|").split("|")] for line in lines]
                content.append("<table><thead><tr>" + "".join("<th>"+html.escape(c)+"</th>" for c in cells[0]) + "</tr></thead><tbody>"
                               + "".join("<tr>"+"".join("<td>"+html.escape(c)+"</td>" for c in row)+"</tr>" for row in cells[2:]) + "</tbody></table>")
            else:
                content.append("<p>"+html.escape(chunk).replace("\n", "<br>")+"</p>")
    content += [f'<figure><img src="figures/{name}.png" alt="{caption}"><figcaption>{caption}</figcaption></figure>' for name,caption in figure_names]
    page = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>'+title+'</title><style>body{font:16px/1.8 system-ui,"Microsoft YaHei",sans-serif;max-width:1100px;margin:40px auto;padding:0 28px;color:#17283b;background:#fcfcfa}h1{font-size:30px}h2{margin-top:38px;color:#164b60}table{border-collapse:collapse;width:100%;font-size:13px}th,td{border-bottom:1px solid #ccd6db;padding:9px;text-align:left}th{background:#edf2f4}figure{margin:40px 0}img{width:100%}figcaption{color:#566777}p{overflow-wrap:anywhere}@media print{body{margin:0}figure{break-inside:avoid}}</style><h1>'+title+'</h1>'+''.join(content)+'</html>'
    (output / "研究报告.html").write_text(page, encoding="utf-8")
    print(json.dumps({"core_complete": len(final), "verified_artifacts": len(evidence), "comparison": comparison,
                      "report": str(output / "研究报告.html")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
