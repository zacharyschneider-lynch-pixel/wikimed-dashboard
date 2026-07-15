import pandas as pd
import math
import os
import argparse


def classify_edit_type(quality_class):
    if quality_class in ("Stub", "Start"):
        return "Expand content"
    elif quality_class == "C":
        return "Improve citations"
    elif quality_class == "B":
        return "Polish & review"
    elif quality_class in ("GA", "FA"):
        return "Maintain / Update"
    return "Expand content"


def classify_difficulty(bytes_val):
    if pd.isna(bytes_val) or bytes_val < 5_000:
        return "Easy"
    elif bytes_val < 30_000:
        return "Medium"
    return "Hard"


def compute_scores(
    input_path="data/wikiproject_medicine.csv",
    output_path="data/scored_articles.csv",
    attention_path="data/attention_signals.csv",
    clickstream_path="data/clickstream_signals.csv",
    tfidf_path="data/tfidf_signals.csv",
):
    df = pd.read_csv(input_path)
    print(f"Loaded {len(df):,} articles from {input_path}")

    # Merge attention signals if available
    has_attention = os.path.exists(attention_path)
    if has_attention:
        att = pd.read_csv(attention_path)
        df = df.merge(att, on="title", how="left")
        print(f"Merged attention signals ({len(att):,} rows)")

    # Merge TF-IDF medical relevance signals if available
    if os.path.exists(tfidf_path):
        tfidf = pd.read_csv(tfidf_path)
        df = df.merge(tfidf, on="title", how="left")
        df["medical_relevance"] = (df["medical_relevance"].fillna(0) * 10).round(1)
        df["top_tfidf_terms"]   = df["top_tfidf_terms"].fillna("")
        print(f"Merged TF-IDF signals ({len(tfidf):,} rows)")

    # Merge clickstream signals if available
    has_clickstream = os.path.exists(clickstream_path)
    if has_clickstream:
        cs = pd.read_csv(clickstream_path)
        df = df.merge(cs, on="title", how="left")
        df["search_arrivals"]   = df["search_arrivals"].fillna(0).astype(int)
        df["search_pct"]        = df["search_pct"].fillna(0)
        df["med_outbound"]      = df["med_outbound"].fillna(0).astype(int)
        df["total_inbound"]     = df["total_inbound"].fillna(0).astype(int)
        print(f"Merged clickstream signals ({len(cs):,} rows)")

    # Fill missing values with conservative defaults
    df["pageviews_12mo"]   = pd.to_numeric(df["pageviews_12mo"],   errors="coerce").fillna(0)
    df["importance_rating"] = pd.to_numeric(df["importance_rating"], errors="coerce").fillna(1)
    df["quality_deficit"]  = pd.to_numeric(df["quality_deficit"],  errors="coerce").fillna(3)
    df["unique_editors"]   = pd.to_numeric(df["unique_editors"],   errors="coerce").fillna(0)
    df["watchers"]         = pd.to_numeric(df["watchers"],         errors="coerce").fillna(0)

    # ── Impact-Need Score ────────────────────────────────────────────────────
    df["pageview_percentile"]   = df["pageviews_12mo"].rank(method="average", pct=True)
    df["importance_norm"]       = (df["importance_rating"] - 1) / 3
    df["quality_deficit_norm"]  = (df["quality_deficit"] - 1) / 4
    df["editor_scarcity_raw"]   = df["unique_editors"].apply(lambda x: 1 / math.log(x + 2))
    df["editor_scarcity_norm"]  = df["editor_scarcity_raw"].rank(method="average", pct=True)

    if has_clickstream:
        # search_pct: what fraction of inbound clicks came from active search
        # (vs. passive discovery via internal Wikipedia links).
        # Percentile-ranked so it contributes proportionally to other signals.
        df["search_intent_pct"] = df["search_pct"].rank(method="average", pct=True)

        raw = (
            df["pageview_percentile"]    * 0.30
            + df["importance_norm"]      * 0.25
            + df["quality_deficit_norm"] * 0.25
            + df["editor_scarcity_norm"] * 0.10
            + df["search_intent_pct"]    * 0.10
        )
    else:
        raw = (
            df["pageview_percentile"]    * 0.35
            + df["importance_norm"]      * 0.25
            + df["quality_deficit_norm"] * 0.25
            + df["editor_scarcity_norm"] * 0.15
        )

    df["impact_need_score"] = (raw / raw.max() * 100).round(1)

    # ── Wiki Attention Score (requires fetch_attention.py data) ──────────────
    if has_attention:
        df["inbound_links"] = pd.to_numeric(df["inbound_links"], errors="coerce").fillna(0)
        df["pageviews_3mo"] = pd.to_numeric(df["pageviews_3mo"], errors="coerce").fillna(0)

        # Velocity: ratio of 3-month rate to 12-month average monthly rate
        # values > 1 = trending up, < 1 = trending down; 0 pageviews → neutral (1.0)
        monthly_avg = df["pageviews_12mo"] / 12
        df["velocity"] = (df["pageviews_3mo"] / 3).where(monthly_avg > 0) / monthly_avg.where(monthly_avg > 0)
        df["velocity"] = df["velocity"].fillna(1.0).clip(upper=10)

        df["pv_pct"]      = df["pageviews_12mo"].rank(method="average", pct=True)
        df["vel_pct"]     = df["velocity"].rank(method="average", pct=True)
        df["links_pct"]   = df["inbound_links"].rank(method="average", pct=True)
        df["watch_pct"]   = df["watchers"].rank(method="average", pct=True)
        df["editor_pct"]  = df["unique_editors"].rank(method="average", pct=True)

        raw_att = (
            df["pv_pct"]      * 0.45
            + df["vel_pct"]   * 0.20
            + df["links_pct"] * 0.20
            + df["watch_pct"] * 0.10
            + df["editor_pct"] * 0.05
        )
        df["wiki_attention_score"] = (raw_att / raw_att.max() * 100).round(1)

        print("\nTop 10 by Wiki Attention Score:")
        top_att = df.nlargest(10, "wiki_attention_score")[
            ["title", "wiki_attention_score", "pageviews_12mo", "velocity", "inbound_links"]
        ]
        print(top_att.to_string(index=False))
    else:
        print("\nNo attention signals found — run fetch_attention.py to compute Wiki Attention Score.")

    df = df.sort_values("impact_need_score", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1

    # Derived fields for dashboard filtering
    df["edit_type"] = df["quality_class"].apply(classify_edit_type)
    if "article_bytes" in df.columns:
        df["difficulty"] = df["article_bytes"].apply(classify_difficulty)
    else:
        df["difficulty"] = "Unknown"

    outdir = os.path.dirname(output_path)
    if outdir:
        os.makedirs(outdir, exist_ok=True)
    df.to_csv(output_path, index=False)

    top = df.head(10)[["rank", "title", "impact_need_score", "quality_class", "pageviews_12mo"]]
    print("\nTop 10 by Impact-Need Score:")
    print(top.to_string(index=False))
    print(f"\nSaved {len(df):,} scored articles to {output_path}")
    return df


def main():
    parser = argparse.ArgumentParser(description="Score WikiProject Medicine articles")
    parser.add_argument("--input",  default="data/wikiproject_medicine.csv")
    parser.add_argument("--output", default="data/scored_articles.csv")
    args = parser.parse_args()
    compute_scores(args.input, args.output)


if __name__ == "__main__":
    main()
