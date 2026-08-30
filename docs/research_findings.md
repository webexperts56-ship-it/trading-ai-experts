# Research Findings: Maximizing Directional-Prediction Accuracy for Multi-Horizon Equity/Crypto Forecasting in Python

**Scope.** PSX equities + crypto (BTC/ETH/SOL/BNB/XRP/DOGE), 7 horizons (1m, 5m, 1h, 6h, 1d, 5d, 1m), current engine = heuristic category-weighting across blended timeframes fused with a single `sklearn.HistGradientBoostingClassifier` per horizon (~15 features from one primary timeframe, no validation, no calibration). This document is the engineering decision reference; section 9 is the prioritized action plan.

**Method.** Live web research (2026): academic papers (NeurIPS 2022, Qlib/MSRA benchmarks, SSRN, IEEE/Elsevier reviews), practitioner benchmarks (Python Data Bench 2026, CFA-style reviews, CodeSOTA), Kasur-style repos, and Lopez de Prado AFML implementations. Sources are linked inline.

---

## 0. Executive summary (TL;DR)

1. **Stay tree-based. Do NOT migrate to LSTM/GRU/TCN/Transformers at ~500 bars.** The strongest 2022–2026 evidence (Grünsztajn et al. NeurIPS 2022 "Why do tree-based models still outperform deep learning on typical tabular data?"; 111-dataset Python Data Bench 2026; Microsoft Qlib CSI300 benchmarks where LightGBM beats LSTM/TFT/iTransformer on engineered tabular factors) says gradient-boosted trees are still the state of the art for tabular, medium-n, high-noise financial forecasting. Deep sequence models only pay off with thousands–tens-of-thousands of bars and GPUs; transformers on financial short-horizon returns *underperform* GBMs after costs in the reviews we found.
2. **The biggest wins are not the algorithm — they are (a) validation, (b) labeling, (c) features, (d) calibration, (e) ensembling.** A 2024 review of 42 studies puts realistic daily-direction accuracy at 55–65% in backtest and 52–56% live after costs. Anything you see claiming >70% on individual names is leakage. The bar you should hold every change against is: *does it survive purged, embargoed walk-forward?*
3. **Concrete highest-leverage moves for this codebase:** replace the single unvalidated HGB model with a **multi-seed LightGBM + XGBoost + logistic-regression ensemble, calibration on a held-out walk-forward fold, and a meta-label/confidence gate**; fix the silent feature-vector/key mismatch; add market-context + volatility + calendar features; purge/embargo all evaluation and label overlapping horizons correctly; report *calibrated* probabilities instead of `tanh`-derived ones.

---

## 1. Model families: which wins for tabular directional prediction

### 1.1 The verdict: gradient-boosted trees

- **Grünsztajn, Oyallon & Varoquaux (NeurIPS 2022, [arXiv:2207.08815](https://arxiv.org/abs/2207.08815))** benchmarked XGBoost, Random Forest, sklearn HistGradientBoosting, MLP, ResNet, FT-Transformer, SAINT on 45 datasets. Result: tree-based models remain state of the art on medium-sized data (~10k rows) *even with heavy hyperparameter search*. Three structural reasons given: NNs are biased to over-smooth target functions, are fragile to uninformative features, and are rotationally invariant (wrong inductive bias for tabular). Your ~500–2,000-row reality sits in the *most* favorable zone for trees.
- **Python Data Bench (Feb 2026, [pythondatabench](https://pythondatabench.com/article/gradient-boosting-python-xgboost-lightgbm-catboost-2026))** — 20 models × 111 datasets: XGBoost/LightGBM/CatBoost "consistently match or outperform deep learning approaches on tabular data."
- **Microsoft Qlib Alpha158 benchmark (CSI300, [qlib benchmarks](https://github.com/microsoft/qlib/tree/main/examples/benchmarks))**: this is the closest public analog to your problem (engineered technical features → cross-sectional return signal). Reported **IC / ICIR** on daily CSI300:
  - Linear: IC 0.0332, ICIR 0.3044
  - LightGBM: **IC 0.0399, ICIR 0.4065** ← best "single" model
  - CatBoost: IC 0.0345 — behind LightGBM on already-numeric features
  - LSTM: IC 0.0318; Transformer-family (TFT, GATs, Localformer, SFM, ALSTM): **all below LightGBM** (TFT IC 0.0358, Localformer 0.0356)
  - **DoubleEnsemble (LGBM base with variance-reduction reweighting): IC 0.0521, ICIR 0.4223** — the winner; this is your ensembling north star (see §5).
  - On **Alpha360** (raw price/volume lags, no engineered features) the DL/spatial models close the gap and some DL wins. **Lesson: feature engineering (Alpha158-style) is what tilts the field toward trees.** Feed transformer-grade models engineered factors and they match you; feed tree models raw bars and they degrade. Engineered factors are the moat — not the model family.
- The much-cited "LSTM beats XGBoost" results are almost universally on *price-level regression* (predicting next close value), which overstates skill because of auto-correlated targets (a 94% "accuracy" LSTM on Tesla in [arXiv:2411.05790](https://arxiv.org/pdf/2411.05790) predicts "next close ≈ today's close"). On *direction classification from engineered features*, GBMs are at parity or better in the systematic reviews ([review of GBM vs NN for stock direction, Elsevier 2026](https://ojs.bonviewpress.com/index.php/FSI/article/download/7630/1823/45477)).

### 1.2 GBDT implementations compared

| Impl | Pros | Cons | Verdict here |
|---|---|---|---|
| **LightGBM** | Fastest training (GOSS/EFB), low memory, leaf-wise; small-data friendly with `min_data_in_leaf`; native categoricals weak but you have none | leaf-wise can overfit tiny n | **Primary model.** `n_estimators` with early stopping; `learning_rate 0.03–0.05`; `num_leaves <= 31`; `min_child_samples = 20–50` on 500–2000 rows |
| **XGBoost** | Second-order approx, histogram method, very predictable defaults, robust sparse handling | Level-wise; slower than LGB | **Co-model in ensemble** for diversity; slightly different bias is the point |
| **CatBoost** | Ordered boosting reduces prediction shift; ambitions on raw categoricals | On pure-numeric small data it lost to LightGBM in the Qlib benchmark (0.0345 vs 0.0399) and is slower | Skip unless you add categorical symbol/exchange features |
| **sklearn HistGradientBoosting** | Good histogram GBDT, no extra dep, fast on <10k rows | Fewer regularization knobs, no native per-class weighting (`class_weight` added recently but thin), no GPU, weak cross-validation hooks | **Fine as a third ensemble member** (it's already in your stack) — keep it, but stop treating it as *the* model |

[TheLinuxCode 2026 comparison](https://thelinuxcode.com/gradientboosting-vs-adaboost-vs-xgboost-vs-catboost-vs-lightgbm-what-really-changes-and-what-i-pick-in-2026) mirrors the practitioner consensus: standard tabular CV protocol = LightGBM/XGBoost + early stopping + monotonic constraints where sensible + probability calibration check. Their "30-minute workflow": validate the split → train LGB/XGB with early stopping → add monotonic constraints + calibration → only then tune hyperparameters. Adopt this order.

Rule of thumb for your size: **with <2k rows, LightGBM with aggressive `min_child_samples`, strong `lambda_l2`, capped `num_leaves`, and early stopping will beat an unconstrained HGB and every NN.** Prediction latency is sub-ms to a few ms per row on CPU ([TheLinuxCode](https://thelinuxcode.com/gradientboosting-vs-adaboost-vs-xgboost-vs-catboost-vs-lightgbm-what-really-changes-and-what-i-pick-in-2026)) — irrelevant to your 60s analyze loop.

### 1.3 Linear baseline (don't skip it)

Qlib shows `Linear` on Alpha158 does IC 0.0332 vs LightGBM 0.0399 — surprisingly close. Ridge/pipeline `LinearRegression` on returns (or `LogisticRegression` for direction + `predict_proba` which is natively well-calibrated enough) is your **de-facto baseline and a great ensemble member**. On small n it is the least overfit model. Benchmark everything against it; if a GBDT can't beat ridge out-of-sample on purged walk-forward by a meaningful margin (and stay above it), the features/labels are wrong, not the model.

### 1.4 LSTM / GRU / TCN

- LSTM vs GRU: close; GRU trains 30–40% faster with ~25% fewer params, LSTM ~does better on volatility/extreme events (ITM 2025 trade-off study). Not worth resolving here.
- **TCN** (dilated causal convs): reaches stable fits faster and matches/beats LSTM for long-range dependency and anomaly tasks ([Bai/Koltun; IEEE/arXiv:2112.09293](https://arxiv.org/pdf/2112.09293)); in financial forecasting surveys it is competitive-to-better than N-BEATS/N-HiTS/TFT and roughly at GRU level (TCN vs LSTM weather/load benchmarks, [TechRxiv 2025](https://www.techrxiv.org/doi/10.36227/techrxiv.176222791.13308024)). None of that changes the decision: **you don't have the data.** Deep nets need large sample + tuning budget; on 500 bars they reliably overfit and their variance across seeds dominates.
- If you ever add a DL arm: **one small GRU or TCN as a *feature extractor* feeding the GBM**, not as the predictor ([crude-oil LSTM+GBM hybrid, JAIT 2025](https://www.jait.us/articles/2025/JAIT-V16N8-1100.pdf)) — the GBM still does the final classification.

### 1.5 Time-series transformers (PatchTST, iTransformer, TimesNet) and foundation models

- These win the **long-horizon, data-rich, strongly-periodic** benchmarks (ETT/M5): PatchTST leads 15/30 in the US-grid benchmark ([arXiv:2602.21415](https://arxiv.org/html/2602.21415v3)) and beats iTransformer/TSMixer on ETT; iTransformer wins when *exogenous variates* matter.
- **For finance specifically:** a 2026 SSRN review ([Limkar/Nabhan/Jain/Treleaven, "Transformer-based Approaches to Financial Time Series"](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6823159)) evaluated PatchTST, iTransformer, TimesNet on short-term stock forecasting and found **TimesNet outperformed the two Transformers — and emphasized the gap between forecasting accuracy and actionable signal.** None of these is competitive with LightGBM on an Alpha158-style factor matrix (Qlib numbers above).
- Foundation models (TimesFM, Chronos, Moirai, Timer, Lag-Llama): zero-shot neighbors of tuned PatchTST on ETTh1 ([CodeSOTA](https://www.codesota.com/guides/time-series-forecasting)); they shine when you have **no** training data, not when you have domain features. Not a fit for directional, feature-rich, cost-sensitive signals.
- **Data-starvation floor:** the CodeSOTA guide's operating rule for deep learning/transformers is ≈**5,000+ observations + GPU**; you have ~500 bars per symbol per timeframe. That is 1.5–2 orders of magnitude below the entry point.

### 1.6 Decision table (this project)

| Model | Accuracy potential @ ~500 bars | Complexity | Latency | Verdict |
|---|---|---|---|---|
| Logistic/ridge baseline | Low–moderate; the calibration anchor | Minimal | µs | **Base member + threshold benchmark** |
| LightGBM / XGBoost (multi-seed) | **Highest practical** | Low | ms | **Primary** |
| sklearn HGB | ~parity with LGB but fewer knobs | Low | ms | Keep as 3rd member |
| RandomForest / ExtraTrees | Good variance-reducer in ensemble; weak solo on finance | Low | ms | Bagging member |
| LSTM/GRU/TCN | Unreliable at this n; needs ≥2–5k bars + tuning | High | ms on CPU | **Skip now**; optional later as feature extractor |
| PatchTST/iTransformer/TimesNet | Only with big data + GPU; not directional-cost-optimal | Very high | ms on GPU | **Skip** |
| TabPFN (in-context tabular LLM) | SOTA on the low-sample frontier (OmniTabBench finds it wins ~mean row-count 2.7k) | Low (off-the-shelf) | s | **Worth a one-off benchmark** as reference, not production |

---

## 2. Feature engineering that actually moves the needle

Anchor: **Qlib's Alpha158 factor family** 🡒 the winning factor taxonomy for tabular financial ML is: (a) price-level *relative* features (close/MA, close/SMA), (b) multi-window returns & momentum, (c) volume relative features (vol/MA(vol), OBV), (d) cross-sectional rank transformations (RSR), (e) scaled/robust normalization. ([Alpha158 in Qlib](https://github.com/microsoft/qlib)).

The 2026 survey + Jansen's ML4T book ch.8 ([ml4trading.io ch.8](https://ml4trading.io/third-edition/chapters/08_financial_features/)) formalize three knobs per feature: **reference frame** (absolute vs relative vs rank), **representation** (level vs return vs z-score), **aggregation** (lookback, decay). Every feature you add must be **point-in-time** (computable at decision time only) and **stationary**; prices are non-stationary, returns/z-scores are the working currency ([feature-engineering-for-finance primer](https://www.quantopia.net/ml-finance/feature-engineering-finance/)).

### 2.1 Classification of what actually works (with evidence)

| Feature family | Why it moves the needle | Concrete spec |
|---|---|---|
| **Multi-horizon z-scored momentum** | Momentum IC is horizon-shaped; z-scoring makes it comparable across regimes and prevents a single huge-move outlier from dominating | `r_h = log(close/close.shift(h))` for h∈{5,10,20,60,…} bars; normalize each by its own rolling std → `mom_z_h` |
| **Range-based realized volatility** | Volatility is *the* most predictable quantity in markets — vol-regime ML hits 68–74% vs 52–56% for direction ([InsigTrade review](https://www.insigtrade.com/blog/how-accurate-is-machine-learning-for-stock-market-prediction)); vol clustering is the strongest stationary signal. **Parkinson/Garman-Klass/Yang-Zhang are 5–14× more efficient than close-to-close variance** ([ML4T ch.8](https://ml4trading.io/third-edition/chapters/08_financial_features/)) | `park=`(log(H/L))², `gk=`, EWMA vol `vol_ew=sqrt(EWMA(r²))`, and their z-scores + 20-bar trend of vol |
| **Volatility-normalized momentum (the MACD-V trick)** | Raw momentum is confounded by vol; vol-normalizing separates "strong trend" from "high vol noise." Spiroglou's MACD-V + regime bands (|z|<50 = ranging, ±50–150 = resumption, >150 = crash) is a principled trend-fidelity feature and a free **ranging-state detector** ([bettersystemtrader](https://bettersystemtrader.com/the-new-indicator-that-improves-momentum-trading-signals-alex-spiroglou/), [SSRN MACD-V](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4099617)) | `vol_norm_mom = roc(h) / tal_vol(h)` per horizon |
| **Relative volume / liquidity** | Volume has fat tails; raw vol dominates features. `vol_ratio` (last/mean20) and OBV-slope are among the highest-importance features in the purged-CV crypto repo ([suenot](https://github.com/suenot/006-ml-training-financial-data): volume_sma_ratio 0.19, zscore_24h 0.16, vol 0.16, momentum 0.145, close_position 0.13, vol_ratio 0.12) | `vol_ratio`, `vol_z`, `obv_slope_5/20`, `dollar_vol` |
| **Cross-sectional / market-context** | **The single cheapest alpha source you're not using.** ML4T ch.8's worked example: SPY-TLT rolling correlation swings momentum's IC by **+17pp** across regimes. Qlib's RSR (cross-sectional rank) and RobustZScoreNorm are standard. Cross-sectional features are robust to non-stationarity (rank order preserved even if levels drift) ([cross-sectional feature math](https://sungchullee.github.io/financial_math_book_writing/ch24/statistical_learning_in_financial_models/feature_engineering_financial_data/)) | per timestamp across the universe of your 14 symbols: `ret_rank_t`, `ret_z_t`, `symbol_ret − universe_median_ret`; plus market level: `BTC_ret_1h`, `universe_mean_ret_1d`, `breadth` (frac up) |
| **Regime features** | Features that are predictive *inside* a regime are the real lever; momentum IC decays monotonically across vol terciles — feed the tercile as a feature/conditioning variable, not as a target | rolling 20-d vol percentile, ADX level, HMM state index (see §6) |
| **Calendar / seasonality** | Equity intraday has a U-shape (first & last hour, lunch lull); crypto has a global UTC pattern with returns peaking ~15:00–16:00 UTC when NY+EU overlap and lowest 01:00–05:00 UTC ([Brauneis et al. RQFA 2024](https://link.springer.com/article/10.1007/s11156-024-01304-1)); day-of-week and month effects are documented even on PSX (Ramadan effect literature) | hour-of-day one-hot (or sin/cos), day-of-week, `is_first_30min`, `is_last_30min`, `is_session_open`, `minutes_to_close`. Cheap and real. |
| **Interactions** | return×vol, momentum×vol, momentum×vol_ratio (commonly top marginal gains in [practitioner feature-engineering writeups](https://www.researchgate.net/publication/392696449_AI-Driven_Feature_Engineering_and_Financial_Analytics_Converging_Insights_from_Machine_Learning_and_Product_Development)) | `mom_z_1h × vol_z`, `r_1d × vol_ratio` |

### 2.2 Stationarity treatments

- Prefer **returns, z-scores, and ratios** (already mostly the case in `ml_feature_vector`).
- **Fractional differencing** (Lopez de Prado AFML ch.5; `mlfinlab`/`mlfinpy` implement it) preserves more memory than first-differencing while achieving stationarity — one of the clear small-sample wins for momentum-style features. Optional; only after the basics land.
- **Never** z-score with full-sample statistics inside backtests (look-ahead). Fit the scaler on each training fold only. Your current `StandardScaler` inside the pipeline is correct only if the pipeline is re-fit per fold — but the whole training currently happens outside any validation, so it **is** currently leaking (see §4).

### 2.3 Concrete gaps to fix in `app/technical/features.py` / `app/signals/model.py` (verified by reading the code)

1. **Feature vector vs FEATURE_KEYS mismatch → silent zeros.** `ml_feature_vector()` returns 15 keys; `FEATURE_KEYS` (model.py) lists 22 including `stoch_d`, `ema20_pct`, `ema50_pct`, `sma200_pct`, `return_1m/5m/15m/1h/4h/1d/5d` — all missing → `predict()` fills them with `0.0` via `.get(k, 0.0)`. You're training on one schema and scoring on a partially-zeros schema. **Unify the schema; better, publish ONE canonical ordered feature namespace used by training, feature extraction, and inference.**
2. `ml_feature_vector` uses only the **primary timeframe** (`primary_df`). Add the blended multi-timeframe features (already computed in `_blended_categories`) plus daily-context features to the ML vector — the engine already blends 5m/15m/1h/1d for the heuristic side; the ML side should see the same multi-scale context (feature engineering is the moat, §1.1).
3. `roc` and momentum features are raw percentages, un-normalized by vol → replace/augment with `mom_z` + `vol_norm_mom`.
4. No clock features exist anywhere → add hour-of-day / day-of-week / session flags per the above table.
5. No cross-sectional/market features → add universe-relative returns and market level (PSX KSE-100 proxy, BTC as crypto market proxy) — the cheapest unclaimed alpha.
6. `bh` volume features: `_volume_score` uses OBV/CMF/manual ratio; fine, but add `vol_z` and `dollar_volume` and their z-scores.

---

## 3. Target labeling for direction classification across horizons

### 3.1 Labeling regimes (ordered by realism)

1. **Fixed-time-horizon sign**: `y = +1 if fwd_ret_H > c else 0`. Simplest, mathematically clean, but labels are pure final-price outcome — the noisiest, most overlap-laden scheme. A fixed-horizon meta-model gave a ROC curve pinned to the diagonal in the MT5 labeling study ([MQL5 Part 2](https://www.mql5.com/en/articles/18864)).
2. **Vol-scaled fixed horizon**: `y = +1 if fwd_ret_H > cost + k·σ_H(pre-estimated), 0 if < −(that), else DROP` (ambiguous zone). Adds "label clarity over signal": you only ask the model to separate economically meaningful moves, and you don't train the model to call coin-flips. Directly implements AFML's `min_ret` idea.
3. **Triple-barrier** ([AFML ch.3, mlfinpy impl](https://mlfinpy.readthedocs.io/en/latest/Labelling.html)): profit-take / stop-loss / vertical barriers scaled by EWMA vol. Path-dependent and risk-aware; the MT5 study shows triple-barrier labels produce a *learnable* ROC where fixed-horizon doesn't. Standard setup: `pt=1·σ, sl=2·σ, t1=horizon`, symmetric for direction; use 1:1 for trend catch and 2:1 for compression.
4. **Meta-labeling** ([mlfinpy](https://mlfinpy.readthedocs.io/en/latest/Labelling.html)): the *secondary* model learns "did the primary signal work?" → output is bet size / confidence ∈[0,1], not direction. **This is the single best structural fit for your existing two-layer system** (heuristic score already proposes direction; ML should learn the conditional probability-of-success, exactly meta-labeling's architecture). It raises precision at the cost of coverage, which is precisely what alert systems want.
5. **Trend-scanning / CTL labels**: continuous-trend labels that extract the dominant trend direction per window; the paper reports superior classification accuracy vs fixed labeling ([MDPI Entropy](https://www.mdpi.com/1099-4300/22/10/1162)). Optional advanced option.

### 3.2 The danger of overlapping multi-output targets (this is a real trap for you)

With horizons of h bars predicted every bar, **each label shares ~h−1 future bars with its neighbors** → effective sample sizes are inflated ~h-fold; adjacent rows are autocorrelated; standard CV treats them as independent and your accuracy estimate inflates (measured +3–8% for naive k-fold on crypto, §4). Consequences and fixes:

- **Loss/overlap-aware evaluation**: any validation split must **purge** training samples whose label interval overlaps a test sample's interval, and **embargo** a buffer of at least the horizon length after each test block (identical to resident-horizon for ARMA features). (AFML ch.7; [walkforge](https://github.com/neeljshah/walkforge); [suenot purging rules](https://github.com/suenot/006-ml-training-financial-data).)
- **Do NOT train one GBM to output all 7 horizons jointly** unless you use a covariance-aware loss (Qlib `DoubleEnsemble` purges by label overlap). Separate models per horizon (as you have) is correct; the overlap problem is inside *each* horizon's dataset.
- **Stagger your training sampling**: for the 1H horizon you do not need a row every minute — resample to every ~15–30 min so consecutive rows' labels no longer overlap 95%; this *reduces* apparent sample size but dramatically increases effective independent sample size. This is the "choosing label clarity over signal" trade in its purest form.

### 3.3 Practical per-horizon scheme for this project

- **1m / 5m (intraday)**: label = vol-scaled fixed horizon with `k≈0.25–0.5` AND require `fwd_ret > transaction cost + impact`; drop ambiguous middle. Expect base rates ≈ 45–55%. Only crypto has true intraday here; PSX intraday via daily-only mode should keep these horizons suppressed (already done in `analyze_daily_only`).
- **1h / 6h**: triple-barrier with vertical barrier = horizon, pt/sl = 1σ/1σ (1.5σ for cleaner labels, fewer samples).
- **1d / 5d**: fixed-horizon with vol-scaled threshold + meta-labeling overlay (meta-label = did a 1σ profit-take hit before the 0.5σ stop for the heuristic signal?). These horizons carry the fund/trend weight and are the realistic "signal" horizons.
- **1mo**: too few independent monthly observations (± 24 over 2 years) to train direction ML; keep heuristic fundamental-led scoring, and use ML only as a **calibrated risk/regime gate**, not a direction source. (Statistically honest: at 1mo you effectively have ~24–48 non-overlapping samples.)

Also: **set the classification threshold at the base rate**, not 0.5. If up-rate is 53%, a "good" model says >53% up; 0.5 is the wrong decision boundary and produces worse-than-random *net* calls after costs.

---

## 4. Validation methodology that prevents lookahead/overfitting

### 4.1 Standard k-fold is broken here — with numbers

From the purged-CV crypto study ([suenot](https://github.com/suenot/006-ml-training-financial-data)): reported vs true out-of-sample accuracy —

| Method | Reported acc | True OOS | Overestimate |
|---|---|---|---|
| K-fold (shuffled) | 0.558 | 0.519 | **+7.5%** |
| K-fold (no shuffle) | 0.542 | 0.524 | +3.4% |
| TimeSeriesSplit | 0.531 | 0.527 | +0.8% |
| **Purged K-fold (1–2% embargo)** | 0.527–0.529 | 0.525–0.526 | +0.4–0.6% |
| Walk-forward (rolling) | 0.524 | 0.522 | +0.4% |
| **Combinatorial Purged CV** | 0.526 | 0.525 | **+0.2%** |

The +3–8% inflation is exactly the band that separates "paper-profitable alert system" from "dead on arrival." **Your current code has no validation loop at all** (`train_and_save` does a single `fit`), so today every reported ML number is in-sample by construction.

### 4.2 The protocol to implement (AFML ch.7/12 + CPCV)

1. **Outer loop = purged & embargoed walk-forward**: `n_splits=5–6`, train on `[t0, t1)`, test on `[t1+h, t1+h+step)` with embargo ≥ horizon (use `max(feature_lookback, horizon)` bars as purge buffer). Every retrain is on the newest sliding/expanding window only.
2. **Inner loop** for hyperparameters: purged K-fold *inside* each training window (never touch the outer test window). Taxonomy per [Quant Lessons](https://5x5x5x5.github.io/quant-lessons/backtest/walk-forward): outer walk-forward defines splits; inner purged CV selects params; retrain on full outer train; score outer test; advance anchor.
3. **CPCV for the final yes/no**: when you must decide "does this pipeline ship?", use combinatorial purged cross-validation with ≥8 groups to get a distribution of paths and compute **PBO (probability of backtest overfitting)** and **DSR (deflated Sharpe)** ([ml4t diagnostic CPCV docs](https://github.com/ml4t/diagnostic/blob/main/docs/methods/cpcv.md); [Neyt/How-To-Backtest-Correctly](https://github.com/Neyt/How-To-Backtest-Correctly)). PBO < 0.3 and DSR > 0.95 are the stated thresholds.
4. **Everything inside the loop**: scalers, missing-value imputation, feature selection (mutual-info / importance-based) must be fit per training fold only — else you leak (this is why the Qlib pipeline puts RobustZScoreNorm inside each fold).

### 4.3 When to retrain (drift)

- **Short horizons (1m/5m/1h)**: vol/regime drift fastest; retrain at least **daily**, or on **drift trigger** — monitor `psi`/`ks` on the top-5 features and retrain when a trigger fires (cheap and standard).
- **1d/5d**: weekly–monthly retrain; keep rolling (e.g., last 500–1000 days) rather than expanding, so the model tracks regime rather than averages regimes.
- **Structural-break triggers**: CUSUM filter on returns (AFML ch.2 sampling; `mlfinlab`) used both for *event sampling* and as a retrain signal. Also track per-regime accuracy and de-activate specialists that stopped paying.
- Always record out-of-sample metrics per fold, per horizon, per regime — you cannot reason about drift without a monitoring table.

### 4.4 Realistic win-rate benchmarks (what to actually aim at)

- Daily-direction ML across 42 studies (2024 JFDS review cited in [InsigTrade](https://www.insigtrade.com/blog/how-accurate-is-machine-learning-for-stock-market-prediction)): **55–65% backtest, 52–56% live after costs/slippage**. Any published >70% on individual names = leakage until proven otherwise.
- Controlled replicates agree: S&P500 RF direction ≈ **51.6%**, Sharpe ~0.41 with 5bp costs ([QuantInsti EPAT](https://www.quantinsti.com/articles/market-direction-prediction-machine-learning-epat-project/)). SPY daily DNN ~57–60% ([Zhong & Enke, Financial Innovation 2019](https://link.springer.com/article/10.1186/s40854-019-0138-0)).
- Human series: Steve Cohen — best trader 63%, most 50–55% ([DayTrading.com](https://www.daytrading.com/winning-percentage)); professional swing/position win rates ~45–60% with R:R > 1.
- Cross-sectional IC reference (Qlib/Alpha158, [benchmark table](https://github.com/microsoft/qlib/tree/main/examples/benchmarks)): **IC ≈ 0.03–0.05, ICIR ≈ 0.35–0.5** for a good daily signal; below ~0.02 IC you are inside noise.
- **Interpretation rule:** at 1m/5m horizons expect ≈50–53% after costs (microstructure noise + taker fees often dominate); 1h–6h ≈ 52–55%; 1d–5d ≈ 54–58% is the *good* zone; 1mo is not ML-solvable at this data size. A "60% confident" alert on crypto 1m is closer to 50/50 — cost that into alert wording (§7).

---

## 5. Probability calibration, imbalance, and ensembling

### 5.1 Calibration (Platt vs isotonic)

- GBDT probabilities are systematically miscalibrated (overconfident); logistic regression is close to calibrated natively. Scikit-learn's `CalibratedClassifierCV` = Platt (sigmoid) or Isotonic (non-parametric) ([sklearn docs](https://scikit-learn.org/stable/modules/calibration.html)).
- **Rule for your n:** isotonic needs ~1,000+ calibration samples and is prone to overfitting step-functions on small sets; Platt scales gracefully down to a few hundred ([probcal trade-offs table](https://inferensys.com/glossary/recursive-error-correction/confidence-scoring-for-outputs/platt-scaling)). With ~500–2,000 rows → **use Platt (logistic on the logit) or even a 1-param temperature/calibration slope**, and fit it **on a held-out purged fold, never on the training rows** (this is the single most common calibration leak; [TrainInData blog](https://www.blog.trainindata.com/probability-calibration-in-machine-learning/)).
- Calibration is *orthogonal* to discrimination: it barely changes AUC but it changes what "60% confidence" *means* — which is the entire contract of your `probability_up` and alerting layer. Report **ECE / reliability diagram** on each walk-forward fold before trusting any probability.
- **Conformal prediction** (split-conformal, model-agnostic) gives empirically-validated confidence sets with tiny cost ([IEEE/conformal LSTM·TCN 2025](https://semanticscholar.org/paper/6e003674da30349b6b74594fa50b337bdfb785ce)) — a clean, defensible way to phrase "this alert's direction call has ≥ 55% coverage-based calibration" and a strong candidate for your confidence field. Cheaper alternative: empirical P(up) per decile from the walk-forward test folds.

### 5.2 Handling imbalance

- Direction labels at 1m–1d are usually only mildly imbalanced (45–55%) because the universe is set by *you* (a mix of momentum and range states). **Don't over-engineer.** Use `scale_pos_weight`/`class_weight='balanced'` only if a horizon strays outside ~40/60.
- **More damaging than imbalance is label noise** (overly-greedy labels, §3). Qlib's **DoubleEnsemble** exists precisely because it reweights samples by purged-covariance variance to suppress label noise and achieved the best IC on Alpha158/Alpha360 ([qlib](https://github.com/microsoft/qlib/tree/main/examples/benchmarks)) — copy the *mechanism* (bagging by resampling n-sample-subsets + purged reweighting) rather than the code.
- Evaluate with **AUC/log-loss and precision-at-threshold**, not raw accuracy. Accuracy rewards predicting the base rate; your alert system needs *precision given an alert fires*.

### 5.3 Ensembling (bagging / stacking / averaging / multi-seed)

- **Multi-seed averaging of LightGBM**: 10–25 seeds averaged on logits (average probabilities, not votes) cuts variance that is *huge* at n=500. This is your cheapest robustness win after validation.
- **Bagging**: subsample rows per model (e.g., 0.7 bootstrap) + random feature subsets; combine via mean of logits. Directly attacks the label-overlap autocorrelation problem (§3) and variance.
- **Heterogeneous blend**: `mean(logistic, LightGBM, XGBoost, HistGB logits)` — Qlib numbers show linear and GBDT are *differently* right (linear IC 0.033, LGB 0.040); their blend typically outperforms either.
- **Stacking**: meta-classifier (ridge/logistic on out-of-fold logits) over base models — slightly better than averaging, needs disciplined OOF generation with purged CV so the meta-model doesn't see leakage. Begin with averaging; escalate to stacking only if OOF-validated gains > ~+1pp.
- **Qlib DoubleEnsemble pattern** as the "next level": two-stage — (1) sample-bagging ensemble, (2) reweight samples by purged cov of residuals, retrain. Reference quality: IC 0.052 vs 0.040 single-LGBM.
- **Blend with the existing heuristic** like you already do — but **calibrate both inputs to the same probability scale first**. Right now `probability_up` = `0.55·tanh(score/55·…)·0.5+0.5` blended with an uncalibrated `ml_p`. Mixing two uncalibrated quantities gives a number that *looks* like a probability but isn't. Convert the score→prob via the empirical mapping from walk-forward folds (or logistic on score), convert ML prob via calibrator, then average with weights ~0.4/0.6 and report ECE.

---

## 6. Regime detection (HMM / trend filters) as a gating layer

- **Gaussian HMM** (`hmmlearn`) on [returns, realized-vol, maybe volume]: standard, robust, 3–5 states map to bull / sideways / bear / high-vol-crisis ([QuantInsti HMM regime blog](https://blog.quantinsti.com/regime-adaptive-trading-python), [paperswithbacktest HMM](https://paperswithbacktest.com/course/hidden-markov-models-trading)). Reserve ≥ 1 year (252+ bars) before trusting it ([hidden-regime](https://github.com/hidden-regime/hidden-regime)).
- **How to use it as a gate (not a signal):**
  1. **Conditional specialists**: train one GBM per regime (trend-ish vs range-ish) and route by HMM state (QuantInsti's walk-forward regime-adaptive RF does exactly this for BTC) — the improvement is real when vol terciles/gates are fed as features per ML4T ch.8 (momentum IC decays across vol terciles).
  2. **Sizing/emission gate**: only emit/surface an alert when the current state's *historical* precision-at-threshold cleared a bar. This "meta-label / gate" is the lowest-risk application and pairs with §5.3.
  3. **Risk overlay**: scale `confidence` by 1/σ(regime) — your existing `vol_penalty` does a rough version; replace with regime-conditional volatility.
- **Cheaper regime proxies that are often as good at n=500** (and fit your `app/trend/regime.py` today): ADX level (already computed), MACD-V ranging bands (§2.1), SMA20/50 structure + slope, realized-vol percentile, Bollinger-band width percentile. A HMM adds state persistence that filters flip-flops — worth adding after the cheap gate is measured.
- **Caveats:** HMM assumes fixed state count and its filtered probabilities lag transitions (probabilistic smoothing) — use Viterbi/posteriors for *diagnosis*, forward-filtered probabilities for *live* gating, and always evaluate the gate's value in walk-forward (a regime gate that is wrong 20% of the time can destroy more than it saves).

---

## 7. Realistic expectations & honest alert framing

- **What is honestly achievable** (evidence-based aggregate):
  - 1m/5m (crypto, after fees + slippage): **≈ 50–53%** net directional hit rate — costs (~5–10bp taker/liquidity + bps of slippage on mid) are a full-time opponent. Do not ship these as standalone signals; treat as intra-session context only (your current `analyze_daily_only` confidence-halving is the right instinct — extend it).
  - 1h/6h: **≈ 53–56%** out-of-sample, optimistically, with good features + validation; precision at alert-threshold can be higher if you gate aggressively.
  - 1d/5d: **≈ 54–58%** is the good zone; this is where tree+feature+ensembling+fundamental-overlay belongs.
  - 1mo: not ML-solvable at ~2 years of data; fundamental/trend heuristic only.
  - Cross-sectional daily IC 0.03–0.05 (Qlib benchmark scale).
- **How to frame alerts so they stay honest:**
  1. Display **calibrated probability and its directional base rate**, not a synthetic score: "P(up 24h) = 0.57 (base 0.53)". Move away from `tanh`-confidence jargon to `calibrated_p ± band` from walk-forward ECE.
  2. **Abstain below threshold.** Optimal decision thresholds come from a risk-coverage curve (coverage vs achievable precision), not from 0.5. Surface fewer, better alerts; make "no alert" a first-class output.
  3. **Decay confidence with horizon and data age** — you already halve intraday confidence in daily-only mode; generalize: freshness decay per timeframe, small-sample penalty per symbol×horizon.
  4. State the **edge as informational**: "this is a conditional probability, not a promise; the strategy's OOS hit-rate at this confidence bucket was X% over the last walk-forward fold." Attach the number to the alert literally.
  5. **Never multiply confidences** from overlapping views as if independent; blend on the probability scale with fixed, calibrated weights.

---

## 8. Open-source implementations worth copying patterns from

1. **[Microsoft Qlib](https://github.com/microsoft/qlib)** — the reference architecture: `Alpha158`/`Alpha360` factor sets, `RobustZScoreNorm + Fillna` per-fold inference, `LightGBM`/`DoubleEnsemble` model zoo, standard IC/ICIR evaluation, walk-forward benchmark harness, online serving/model-rolling. Copy: the factor taxonomy + the per-fold normalization + the benchmark/metrics table.
2. **[mlfinlab / mlfinpy](https://mlfinpy.readthedocs.io/en/latest/)** — Lopez de Prado reference implementations: triple-barrier & meta-labeling (`labeling`), purged/embargoed CV, fractional differencing, CUSUM event sampling, feature-importance-by-MDA. Copy: labeling + validation snippets (they're short and MIT/Apache).
3. **[suenot/006-ml-training-financial-data](https://github.com/suenot/006-ml-training-financial-data)** — end-to-end crypto tabular ML with the *measured* k-fold-leak table (§4.1), purge/embargo implementation in ~50 lines, and a feature-importance ranking consistent with ours (volume + vol-z + momentum-z + close-position top the list). Copy: the splitter + feature list.
4. **[Neyt/How-To-Backtest-Correctly](https://github.com/Neyt/How-To-Backtest-Correctly)** and **[ml4t/diagnostic](https://github.com/ml4t/diagnostic)** — cleaned AFML tooling: PurgedKFold, CPCV, DSR/PBO calculators, calendar-aware splitters that skip non-trading days (important for PSX weekend gaps). Copy: the CPCV/DSR gate for go/no-go decisions.
5. **[stefan-jansen machine-learning-for-trading](https://github.com/stefan-jansen/machine-learning-for-trading)** (+ zipline-reloaded) and his **ML4T 3rd-edition ch.8** ([ml4trading.io](https://ml4trading.io/third-edition/chapters/08_financial_features/)) — best single source for the *feature-specification discipline* (reference frame / representation / aggregation, signal-vs-state roles, interaction templates like gating/scaling). Copy: the feature-spec template and the "budget variants by family" rule.
6. **[walkforge](https://github.com/neeljshah/walkforge)** / **[walkforward backtest notebooks](https://5x5x5x5.github.io/quant-lessons/backtest/walk-forward)** — drop-in walk-forward + purged-k-fold sklearn-compatible splitters; exactly the validation layer `app/signals/model.py` is missing.
7. **Fine to skip for now**: Nixtla `neuralforecast` (PatchTST/iTransformer/N-HiTS) and time-series foundation-model stacks (Chronos/TimesFM/Moirai) — revisit only if a *data-rich* deep arm is ever justified (§1.5).

---

## 9. Prioritized implementation plan for this scikit-learn pipeline

Ordered by (value ÷ effort). Each maps to files in `app/`.

1. **Fix the silent feature-schema mismatch and unify one canonical feature namespace** (`app/technical/features.py` ↔ `app/signals/model.py`). Highest integrity-per-effort; currently training on one schema, scoring on another (zeros fill the rest).
2. **Build the purged & embargoed walk-forward harness** (new module, e.g. `app/ml/validation.py`): outer walk-forward (≈6 splits, embargo ≥ horizon), inner purged K-fold for hyperparams, per-fold scaler fit, report AUC/log-loss/accuracy/ECE per fold + monotonic precision-vs-threshold curve. Converts every future change into a *measurable* one. (Copy patterns from walkforge / suenot.)
3. **Upgrade the model to a multi-seed LightGBM + XGBoost + logistic blend with Platt calibration on a held-out purged fold** (`app/signals/model.py`): average logits across ~10 seeds; fit calibrator ONLY on the 2nd-layer fold; serialize calibrators; keep HGB as a 3rd member. Replaces single uncalibrated `HistGradientBoostingClassifier(max_iter=200)`.
4. **Add the high-leverage feature families**: multi-horizon vol-z'd momentum (`mom_z_h`, `vol_norm_mom`), range-based vol (Parkinson/GK/EWMA) + vol regime percentile, relative volume & dollar vol, **calendar features** (hour-of-day / day-of-week / session flags), **cross-sectional/market-context** (universe-rank/z, market-level returns, breadth), and label the whole thing with a per-horizon vol-scaled threshold + drop-ambiguous zone (§2.3).
5. **Change labeling + evaluation jointly**: per-horizon vol-scaled labels (or triple-barrier for 1h/6h), resample intraday training rows so consecutive labels barely overlap, and a **meta-label gate** that learns P(primary-signal-correct) and drives alert emission + confidence (this is the natural upgrade of the current 0.55/0.45 heuristic↔ML blend). Then hard-code the honest alert contract: calibrated probability + base rate + OOS hit-rate per confidence bucket (§7). Last, add the HMM/cheap-regime gate (§6).

Recommended sequencing: **1 → 2 → 3 → 4 → 5** — validation before models, labels alongside features, and the regime/meta-gate only after the core is measurable.

---

### References (key links)
- Trees beat DL on tabular: Grünsztajn et al., NeurIPS 2022 — https://arxiv.org/abs/2207.08815
- 111-dataset boosting benchmark 2026 — https://pythondatabench.com/article/gradient-boosting-python-xgboost-lightgbm-catboost-2026
- Microsoft Qlib Alpha158/360 benchmarks — https://github.com/microsoft/qlib/tree/main/examples/benchmarks
- Transformers for financial TS review (TimesNet>PatchTST/iTransformer on short-term) — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6823159
- PatchTST/iTransformer/foundation models vs classical — https://www.codesota.com/guides/time-series-forecasting
- Feature engineering for finance (ML4T 3rd ed. ch.8; Alpha158-style specs, vol efficiency) — https://ml4trading.io/third-edition/chapters/08_financial_features/ ; https://github.com/microsoft/qlib
- MACD-V volatility-normalized momentum + ranging definition — https://bettersystemtrader.com/the-new-indicator-that-improves-momentum-trading-signals-alex-spiroglou/ ; https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4099617
- Crypto intraday time-of-day patterns (UTC) — https://link.springer.com/article/10.1007/s11156-024-01304-1
- Labeling: triple-barrier & meta-labeling (AFML impl) — https://mlfinpy.readthedocs.io/en/latest/Labelling.html
- Measured k-fold leakage + purge/embargo — https://github.com/suenot/006-ml-training-financial-data
- CPCV / PBO / DSR — https://github.com/ml4t/diagnostic/blob/main/docs/methods/cpcv.md ; https://github.com/Neyt/How-To-Backtest-Correctly
- Walk-forward protocol — https://5x5x5x5.github.io/quant-lessons/backtest/walk-forward ; https://github.com/neeljshah/walkforge
- Realistic ML direction accuracy (52–65%, live degradation) — https://www.insigtrade.com/blog/how-accurate-is-machine-learning-for-stock-market-prediction
- HMM regime detection — https://blog.quantinsti.com/regime-adaptive-trading-python ; https://paperswithbacktest.com/course/hidden-markov-models-trading
- Probability calibration trade-offs — https://scikit-learn.org/stable/modules/calibration.html ; https://inferensys.com/glossary/recursive-error-correction/confidence-scoring-for-outputs/platt-scaling