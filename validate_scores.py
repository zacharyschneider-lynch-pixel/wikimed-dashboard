import pandas as pd

df = pd.read_csv("data/scored_articles.csv")
print(f"Total articles: {len(df):,}")
print(f"With impact_need_score: {df['impact_need_score'].notna().sum():,}")
print(f"With quality_class:     {df['quality_class'].notna().sum():,}")
print(f"With importance_label:  {df['importance_label'].notna().sum():,}")

# ── All-article distributions ─────────────────────────────────────────────────
print("\n=== QUALITY (all articles) ===")
q_all = df["quality_class"].value_counts()
q_all_pct = df["quality_class"].value_counts(normalize=True).mul(100).round(1)
for k in q_all.index:
    print(f"  {k:<8} {q_all[k]:>6,}  ({q_all_pct[k]:.1f}%)")

print("\n=== IMPORTANCE (all articles) ===")
i_all = df["importance_label"].value_counts()
i_all_pct = df["importance_label"].value_counts(normalize=True).mul(100).round(1)
for k in i_all.index:
    print(f"  {k:<8} {i_all[k]:>6,}  ({i_all_pct[k]:.1f}%)")

# ── Top 100 ───────────────────────────────────────────────────────────────────
top100 = df.nlargest(100, "impact_need_score")

print("\n=== QUALITY (top 100 by Impact-Need Score) ===")
q_top = top100["quality_class"].value_counts()
for k in q_top.index:
    print(f"  {k:<8} {q_top[k]:>3}")

print("\n=== IMPORTANCE (top 100 by Impact-Need Score) ===")
i_top = top100["importance_label"].value_counts()
for k in i_top.index:
    print(f"  {k:<8} {i_top[k]:>3}")

# ── Summary ───────────────────────────────────────────────────────────────────
stub_start_all = df["quality_class"].isin(["Stub", "Start"]).mean() * 100
stub_start_top = top100["quality_class"].isin(["Stub", "Start"]).mean() * 100
high_top_all   = df["importance_label"].isin(["High", "Top"]).mean() * 100
high_top_top   = top100["importance_label"].isin(["High", "Top"]).mean() * 100

print("\n=== KEY VALIDATION NUMBERS ===")
print(f"Stub/Start quality  — all articles : {stub_start_all:.1f}%")
print(f"Stub/Start quality  — top 100      : {stub_start_top:.1f}%")
print(f"High/Top importance — all articles : {high_top_all:.1f}%")
print(f"High/Top importance — top 100      : {high_top_top:.1f}%")

print("\n--- Top 10 articles by Impact-Need Score ---")
cols = ["title", "quality_class", "importance_label", "impact_need_score"]
print(top100[cols].head(10).to_string(index=False))
