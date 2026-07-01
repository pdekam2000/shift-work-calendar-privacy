# راهنمای نسخه اسکالپ 1 دقیقه ای

> نتیجه مهم: در تست های اخیر، نسخه M1 سودده پایدار پیدا نشد. این preset فقط برای
> Strategy Tester و حساب Demo است و برای Live توصیه نمی شود.

## فایل های نسخه M1

- Expert Advisor مشترک:
  - `mt5/Experts/ForexBreakoutPullbackEA.mq5`
- preset مخصوص M1:
  - `mt5/Presets/M1_Scalping_Experimental_NOT_RECOMMENDED_FOR_LIVE.set`
- پارامترها و نتیجه تست:
  - `config/m1_scalping_experimental_params.json`
  - `results/m1_scalping_experimental_summary.json`

## نتیجه تست

با هزینه واقع بینانه:

- اسپرد: `0.8 pip`
- اسلیپیج: `0.1 pip`
- سرمایه: `100 EUR`
- ریسک: `0.5%`
- نتیجه بهترین جستجو روی 4 جفت: `-9.32 EUR`

با فرض حساب Raw Spread خیلی خوب:

- اسپرد: `0.2 pip`
- اسلیپیج: `0.03 pip`
- نتیجه بهترین جستجو: `-10.84 EUR`

پس فعلا این نسخه را سودده حساب نمی کنیم.

## اگر خواستی فقط دمو تست کنی

1. فایل EA را در `MQL5/Experts` کپی کن.
2. فایل preset را در `MQL5/Presets` کپی کن.
3. در MT5 Strategy Tester:
   - Expert: `ForexBreakoutPullbackEA`
   - Timeframe: `M1`
   - Symbol: اول فقط `EURUSD`
   - Model: `Every tick based on real ticks`
4. در Inputs دکمه `Load` را بزن و فایل زیر را انتخاب کن:
   - `M1_Scalping_Experimental_NOT_RECOMMENDED_FOR_LIVE.set`
5. فقط اگر در بروکر خودت با داده real ticks مثبت شد، روی Demo تست کن.

## اگر هیچ معامله ای باز نشد

- `InpEnableDiagnostics=true` را فعال کن.
- لاگ های `[FBP_DIAG]` را در تب `Experts` و `Journal` بخوان.
- برای تست اجازه معامله فقط روی Demo می توانی `ForceTestTrade=true` کنی.
- ForceTestTrade فقط یک سفارش `0.01 lot` باز می کند، آن هم فقط اگر حساب Demo باشد و بروکر حجم دقیق `0.01` را قبول کند.

## پیشنهاد من

برای استفاده جدی تر، فعلا نسخه H4 بهتر است. نسخه M1 را فقط برای تحقیق و تست بیشتر نگه دار.
