# محتویات بسته دانلودی

این بسته برای بک تست و اجرای دمو روی MetaTrader 5 آماده شده است.

## فایل های اصلی

- `mt5/Experts/ForexBreakoutPullbackEA.mq5`
  - Expert Advisor برای MetaTrader 5
  - منطق H4 breakout-pullback با ATR/EMA/RSI/ADX و سه سطح TP
  - پنل نمایشی روی چارت با نام مالک، لوگوی رنگی DRAGON FX و وضعیت کار ربات

- `docs/MT5_RUN_GUIDE_FA.md`
  - راهنمای فارسی نصب، compile، بک تست و اجرای دمو در MT5

- `config/final_4h_three_pair_params.json`
  - پارامترهای نهایی بک تست شده

- `mt5/Presets/H4_Breakout_Pullback_Recommended.set`
  - preset آماده MT5 برای ربات اصلی H4
  - شامل diagnostics روشن و ForceTestTrade خاموش

- `results/focused_final_package_summary.json`
  - خلاصه نتیجه نهایی بک تست و walk-forward

- `mt5/Presets/M1_Scalping_Experimental_NOT_RECOMMENDED_FOR_LIVE.set`
  - preset آزمایشی برای اسکالپ 1 دقیقه ای
  - طبق تست فعلی برای Live توصیه نمی شود

- `docs/M1_SCALPING_RESEARCH_FA.md`
  - توضیح نتیجه تست M1 و روش تست دمو

- `forex_robot/`
  - کد Python برای بک تست و بهینه سازی

- `README.md`
  - راهنمای کلی پروژه

## پیشنهاد شروع

1. اول راهنمای `docs/MT5_RUN_GUIDE_FA.md` را بخوان.
2. در MT5 فقط `EURUSD H4` را تست کن.
3. بعد `AUDUSD H4` و سپس `GBPUSD H4` را اضافه کن.
4. حساب واقعی را فقط بعد از تست دمو و با ریسک پایین در نظر بگیر.
