//+------------------------------------------------------------------+
//|                                                                  |
//|          ██████╗ ██████╗  █████╗  ██████╗  ██████╗ ███╗   ██╗   |
//|          ██╔══██╗██╔══██╗██╔══██╗██╔════╝ ██╔═══██╗████╗  ██║   |
//|          ██║  ██║██████╔╝███████║██║  ███╗██║   ██║██╔██╗ ██║   |
//|          ██║  ██║██╔══██╗██╔══██║██║   ██║██║   ██║██║╚██╗██║   |
//|          ██████╔╝██║  ██║██║  ██║╚██████╔╝╚██████╔╝██║ ╚████║   |
//|          ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═══╝  |
//|                         F  X                                     |
//|                                                                  |
//|                   PEDRAM KAMANGAR — ROBOT 1                      |
//|         استراتژی: SAR + Ichimoku + RSI Gate                      |
//|         نسخه: 2.0.0  |  تاریخ: 2026                             |
//+------------------------------------------------------------------+
#property copyright   "Pedram Kamangar — Dragon FX"
#property link        "https://github.com/pdekam2000"
#property version     "2.00"
#property description "Dragon FX Robot 1 — SAR+Ichimoku+RSI Gate"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

//══════════════════════════════════════════════════════════════════
//  ورودی‌ها
//══════════════════════════════════════════════════════════════════
input group "═══════ مدیریت سرمایه ═══════"
input double RiskPercent   = 1.5;
input double MaxLot        = 2.0;
input double MinLot        = 0.01;

input group "═══════ پارامترهای استراتژی ═══════"
input int    ADX_Period    = 14;
input double ADX_MinLevel  = 22.0;
input int    RSI_Period    = 14;
input double RSI_BuyMin    = 40.0;
input double RSI_BuyMax    = 68.0;
input double RSI_SellMin   = 32.0;
input double RSI_SellMax   = 60.0;
input double ATR_SL_Mult   = 1.3;
input int    ATR_Period    = 14;
input double MaxSpreadPips = 3.0;   // حداکثر اسپرد مجاز

input group "═══════ Take Profit سه‌گانه ═══════"
input double TP1_RR        = 1.0;
input double TP2_RR        = 2.0;
input double TP3_RR        = 3.0;
input double TP1_Percent   = 33.0;
input double TP2_Percent   = 33.0;

input group "═══════ Ichimoku ═══════"
input int    Ichi_Tenkan   = 9;
input int    Ichi_Kijun    = 26;
input int    Ichi_Senkou   = 52;

input group "═══════ Parabolic SAR ═══════"
input double SAR_Step      = 0.02;
input double SAR_Max       = 0.2;

input group "═══════ تنظیمات معاملاتی ═══════"
input int    Magic         = 20260001;
input int    Slippage      = 30;
input bool   EnableTrading = true;

input group "═══════ Debug / تست ═══════"
input bool   DebugMode     = true;    // لاگ کامل عیب‌یابی
input bool   ForceTestTrade= false;   // فقط Demo: یک معامله 0.01 lot آزمایشی

input group "═══════ پنل نمایش ═══════"
input bool   ShowPanel     = true;
input int    PanelX        = 15;
input int    PanelY        = 15;

//══════════════════════════════════════════════════════════════════
//  متغیرهای کلی
//══════════════════════════════════════════════════════════════════
CTrade        Trade;
CPositionInfo PosInfo;

int      h_SAR, h_Ichi, h_RSI, h_ADX, h_ATR;
datetime LastBarTime  = 0;
int      TotalTrades  = 0;
double   TotalProfit  = 0.0;
int      WinTrades    = 0;
string   LastSignal   = "---";
string   LastAction   = "در انتظار سیگنال";
bool     IsActive     = false;
bool     TestDone     = false;   // برای ForceTestTrade
int      TickCount    = 0;

//══════════════════════════════════════════════════════════════════
//  OnInit
//══════════════════════════════════════════════════════════════════
int OnInit()
  {
   Trade.SetExpertMagicNumber(Magic);
   Trade.SetDeviationInPoints(Slippage);
   Trade.SetTypeFilling(ORDER_FILLING_IOC);

   h_SAR  = iSAR(_Symbol,  PERIOD_D1, SAR_Step, SAR_Max);
   h_Ichi = iIchimoku(_Symbol, PERIOD_D1, Ichi_Tenkan, Ichi_Kijun, Ichi_Senkou);
   h_RSI  = iRSI(_Symbol,  PERIOD_D1, RSI_Period, PRICE_CLOSE);
   h_ADX  = iADX(_Symbol,  PERIOD_D1, ADX_Period);
   h_ATR  = iATR(_Symbol,  PERIOD_D1, ATR_Period);

   if(h_SAR==INVALID_HANDLE || h_Ichi==INVALID_HANDLE ||
      h_RSI==INVALID_HANDLE || h_ADX==INVALID_HANDLE  ||
      h_ATR==INVALID_HANDLE)
     {
      DBG("❌ خطا: اندیکاتورها بارگذاری نشدند");
      Alert("Robot1: خطا در بارگذاری اندیکاتورها!");
      return INIT_FAILED;
     }

   // بررسی ForceTestTrade روی Real
   if(ForceTestTrade && AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_REAL)
     {
      Alert("⛔ ForceTestTrade فقط روی Demo مجاز است!");
      DBG("⛔ ForceTestTrade روی Real اجرا نشد — ایمنی فعال");
      return INIT_FAILED;
     }

   if(ShowPanel) DrawPanel();
   DBG("✅ Robot1 راه‌اندازی شد — نسخه 2.0 | Dragon FX");
   DBG("   Symbol=" + _Symbol + " | TF=D1 | Magic=" + IntegerToString(Magic));
   DBG("   Risk=" + DoubleToString(RiskPercent,1) + "% | ADX>=" + DoubleToString(ADX_MinLevel,0));
   DBG("   TP1=" + DoubleToString(TP1_RR,1) + "R TP2=" + DoubleToString(TP2_RR,1) + "R TP3=" + DoubleToString(TP3_RR,1) + "R");
   if(ForceTestTrade) DBG("⚠ ForceTestTrade=true — یک معامله آزمایشی 0.01 lot اجرا خواهد شد");

   return INIT_SUCCEEDED;
  }

//══════════════════════════════════════════════════════════════════
//  OnDeinit
//══════════════════════════════════════════════════════════════════
void OnDeinit(const int reason)
  {
   IndicatorRelease(h_SAR);  IndicatorRelease(h_Ichi);
   IndicatorRelease(h_RSI);  IndicatorRelease(h_ADX);
   IndicatorRelease(h_ATR);
   ObjectsDeleteAll(0, "PK_");
   Comment("");
   DBG("Robot1 متوقف شد.");
  }

//══════════════════════════════════════════════════════════════════
//  OnTick — نقطه ورود اصلی
//══════════════════════════════════════════════════════════════════
void OnTick()
  {
   if(!EnableTrading) return;
   TickCount++;
   if(DebugMode && TickCount % 500 == 1)
      DBG("── Tick #" + IntegerToString(TickCount) + " | bid=" +
          DoubleToString(SymbolInfoDouble(_Symbol,SYMBOL_BID),5) + " ──");

   // ── ForceTestTrade (فقط Demo) ─────────────────────────────────
   if(ForceTestTrade && !TestDone)
     {
      if(AccountInfoInteger(ACCOUNT_TRADE_MODE) != ACCOUNT_TRADE_MODE_REAL)
        {
         DBG("🔬 ForceTestTrade: باز کردن معامله آزمایشی 0.01 lot...");
         RunForceTest();
         TestDone = true;
        }
      return;
     }

   // ── بررسی کندل جدید (Daily) ──────────────────────────────────
   datetime barTime = iTime(_Symbol, PERIOD_D1, 0);
   if(barTime == LastBarTime)
     {
      ManageOpenPositions();
      if(ShowPanel) UpdatePanel();
      return;
     }

   DBG("══ کندل روزانه جدید: " + TimeToString(barTime, TIME_DATE) + " ══");
   LastBarTime = barTime;
   IsActive    = true;

   CheckSignal();
   ManageOpenPositions();
   if(ShowPanel) UpdatePanel();
  }

//══════════════════════════════════════════════════════════════════
//  بررسی سیگنال — با لاگ کامل
//══════════════════════════════════════════════════════════════════
void CheckSignal()
  {
   // ── 1. تایم‌فریم ──────────────────────────────────────────────
   DBG("[1] Timeframe check: D1 ✓ (بررسی روی " + _Symbol + ")");

   // ── 2. اسپرد ─────────────────────────────────────────────────
   double spread = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD) * _Point / 0.0001;
   DBG("[2] Spread check: spread=" + DoubleToString(spread,1) +
       " pip | max=" + DoubleToString(MaxSpreadPips,1) + " pip");
   if(spread > MaxSpreadPips)
     {
      DBG("   ❌ اسپرد خیلی زیاد — معامله لغو شد");
      LastAction = "اسپرد زیاد: " + DoubleToString(spread,1) + " pip";
      return;
     }
   DBG("   ✓ اسپرد قابل قبول");

   // ── 3. دریافت اندیکاتورها ─────────────────────────────────────
   double sar[];     ArraySetAsSeries(sar,     true);
   double tenkan[];  ArraySetAsSeries(tenkan,  true);
   double kijun[];   ArraySetAsSeries(kijun,   true);
   double senkouA[]; ArraySetAsSeries(senkouA, true);
   double senkouB[]; ArraySetAsSeries(senkouB, true);
   double rsi[];     ArraySetAsSeries(rsi,     true);
   double adxMain[]; ArraySetAsSeries(adxMain, true);
   double atr[];     ArraySetAsSeries(atr,     true);
   double close[];   ArraySetAsSeries(close,   true);
   double plusDI[];  ArraySetAsSeries(plusDI,  true);
   double minusDI[]; ArraySetAsSeries(minusDI, true);

   if(CopyBuffer(h_SAR,  0, 0, 3, sar)     < 3) { DBG("❌ SAR data خطا");     return; }
   if(CopyBuffer(h_Ichi, 0, 0, 3, tenkan)  < 3) { DBG("❌ Tenkan data خطا");  return; }
   if(CopyBuffer(h_Ichi, 1, 0, 3, kijun)   < 3) { DBG("❌ Kijun data خطا");   return; }
   if(CopyBuffer(h_Ichi, 2, 0, 3, senkouA) < 3) { DBG("❌ SenkouA data خطا"); return; }
   if(CopyBuffer(h_Ichi, 3, 0, 3, senkouB) < 3) { DBG("❌ SenkouB data خطا"); return; }
   if(CopyBuffer(h_RSI,  0, 0, 3, rsi)     < 3) { DBG("❌ RSI data خطا");     return; }
   if(CopyBuffer(h_ADX,  0, 0, 3, adxMain) < 3) { DBG("❌ ADX data خطا");     return; }
   if(CopyBuffer(h_ADX,  1, 0, 3, plusDI)  < 3) { DBG("❌ +DI data خطا");     return; }
   if(CopyBuffer(h_ADX,  2, 0, 3, minusDI) < 3) { DBG("❌ -DI data خطا");     return; }
   if(CopyBuffer(h_ATR,  0, 0, 3, atr)     < 3) { DBG("❌ ATR data خطا");     return; }
   if(CopyClose(_Symbol, PERIOD_D1, 0, 3, close) < 3) { DBG("❌ Close data خطا"); return; }

   double price    = close[1];
   double atrVal   = atr[1];
   double rsiVal   = rsi[1];
   double adxVal   = adxMain[1];
   double sarCur   = sar[1];
   double sarPrev  = sar[2];
   double closePrev= close[2];
   double cloudTop = MathMax(senkouA[1], senkouB[1]);
   double cloudBot = MathMin(senkouA[1], senkouB[1]);

   // ── 4. Session filter (D1 = همیشه OK) ────────────────────────
   DBG("[3] Session filter: D1 — همه ساعات ✓");

   // ── 5. مقادیر اندیکاتور ──────────────────────────────────────
   DBG("[4] Indicator values:");
   DBG("    Close[1]=" + DoubleToString(price,5) +
       " | SAR[1]=" + DoubleToString(sarCur,5) + " SAR[2]=" + DoubleToString(sarPrev,5));
   DBG("    Tenkan=" + DoubleToString(tenkan[1],5) +
       " | Kijun=" + DoubleToString(kijun[1],5));
   DBG("    Cloud TOP=" + DoubleToString(cloudTop,5) +
       " | Cloud BOT=" + DoubleToString(cloudBot,5));
   DBG("    RSI=" + DoubleToString(rsiVal,2) +
       " | ADX=" + DoubleToString(adxVal,2) +
       " | +DI=" + DoubleToString(plusDI[1],2) +
       " | -DI=" + DoubleToString(minusDI[1],2));
   DBG("    ATR=" + DoubleToString(atrVal,5));

   // ── 6. ADX check ─────────────────────────────────────────────
   DBG("[5] ADX check: ADX=" + DoubleToString(adxVal,2) + " >= " + DoubleToString(ADX_MinLevel,0) + " ?");
   if(adxVal < ADX_MinLevel)
     {
      DBG("   ❌ ADX خیلی ضعیف — بدون سیگنال");
      LastAction = "ADX ضعیف: " + DoubleToString(adxVal,1);
      return;
     }
   DBG("   ✓ ADX کافی است");

   // ── 7. SAR flip ───────────────────────────────────────────────
   bool sarFlipUp = (sarCur < price) && (sarPrev > closePrev);
   bool sarFlipDn = (sarCur > price) && (sarPrev < closePrev);
   DBG("[6] SAR flip: Up=" + (sarFlipUp ? "YES" : "NO") +
       " | Down=" + (sarFlipDn ? "YES" : "NO"));

   // ── 8. Ichimoku ───────────────────────────────────────────────
   bool aboveCloud = price > cloudTop;
   bool belowCloud = price < cloudBot;
   bool tkBull     = tenkan[1] > kijun[1];
   bool tkBear     = tenkan[1] < kijun[1];
   DBG("[7] Ichimoku: AboveCloud=" + (aboveCloud?"YES":"NO") +
       " | BelowCloud=" + (belowCloud?"YES":"NO") +
       " | TK_Bull=" + (tkBull?"YES":"NO") +
       " | TK_Bear=" + (tkBear?"YES":"NO"));

   // ── 9. RSI zone ──────────────────────────────────────────────
   bool rsiBuy  = (rsiVal >= RSI_BuyMin  && rsiVal <= RSI_BuyMax);
   bool rsiSell = (rsiVal >= RSI_SellMin && rsiVal <= RSI_SellMax);
   DBG("[8] RSI check: RSI=" + DoubleToString(rsiVal,2) +
       " | Buy_zone(" + DoubleToString(RSI_BuyMin,0) + "-" + DoubleToString(RSI_BuyMax,0) + ")=" +
       (rsiBuy?"YES":"NO") +
       " | Sell_zone(" + DoubleToString(RSI_SellMin,0) + "-" + DoubleToString(RSI_SellMax,0) + ")=" +
       (rsiSell?"YES":"NO"));

   // ── 10. سیگنال نهایی ─────────────────────────────────────────
   bool buySignal  = sarFlipUp && aboveCloud && tkBull && rsiBuy;
   bool sellSignal = sarFlipDn && belowCloud && tkBear && rsiSell;

   DBG("[9] Signal result:");
   DBG("    BUY  signal = SAR_Up(" + (sarFlipUp?"✓":"✗") + ") + AboveCloud(" + (aboveCloud?"✓":"✗") +
       ") + TK_Bull(" + (tkBull?"✓":"✗") + ") + RSI_Buy(" + (rsiBuy?"✓":"✗") + ") → " +
       (buySignal ? "✅ BUY!" : "❌ نه"));
   DBG("    SELL signal = SAR_Dn(" + (sarFlipDn?"✓":"✗") + ") + BelowCloud(" + (belowCloud?"✓":"✗") +
       ") + TK_Bear(" + (tkBear?"✓":"✗") + ") + RSI_Sell(" + (rsiSell?"✓":"✗") + ") → " +
       (sellSignal ? "✅ SELL!" : "❌ نه"));

   // ── 11. ارسال سفارش ──────────────────────────────────────────
   if(buySignal)
     {
      LastSignal = "BUY ▲";
      if(CountMyPositions(POSITION_TYPE_BUY) > 0)
        {
         DBG("[10] Order: خرید باز قبلاً وجود دارد — رد شد");
         return;
        }
      double sl = price - atrVal * ATR_SL_Mult;
      DBG("[10] Order attempt: BUY | SL=" + DoubleToString(sl,5) +
          " | ATR=" + DoubleToString(atrVal,5) + " | Mult=" + DoubleToString(ATR_SL_Mult,1));
      OpenThreePartOrder(ORDER_TYPE_BUY, price, sl, atrVal);
     }
   else if(sellSignal)
     {
      LastSignal = "SELL ▼";
      if(CountMyPositions(POSITION_TYPE_SELL) > 0)
        {
         DBG("[10] Order: فروش باز قبلاً وجود دارد — رد شد");
         return;
        }
      double sl = price + atrVal * ATR_SL_Mult;
      DBG("[10] Order attempt: SELL | SL=" + DoubleToString(sl,5) +
          " | ATR=" + DoubleToString(atrVal,5) + " | Mult=" + DoubleToString(ATR_SL_Mult,1));
      OpenThreePartOrder(ORDER_TYPE_SELL, price, sl, atrVal);
     }
   else
     {
      DBG("[10] Order: سیگنالی نیست — بدون معامله");
      LastAction = "بدون سیگنال";
     }
  }

//══════════════════════════════════════════════════════════════════
//  باز کردن ۳ پوزیشن برای TP سه‌گانه
//══════════════════════════════════════════════════════════════════
void OpenThreePartOrder(ENUM_ORDER_TYPE type, double price, double sl, double atrVal)
  {
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double slDist  = MathAbs(price - sl);
   double slPips  = slDist / _Point / 10.0;
   if(slPips < 3) slPips = 10;

   double pipVal  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE) * 10;
   if(pipVal <= 0) pipVal = 10;

   double riskAmt  = balance * RiskPercent / 100.0;
   double totalLot = NormalizeDouble(riskAmt / (slPips * pipVal), 2);
   totalLot = MathMax(MinLot * 3, MathMin(MaxLot, totalLot));

   double lot1 = NormalizeDouble(totalLot * TP1_Percent / 100.0, 2);
   double lot2 = NormalizeDouble(totalLot * TP2_Percent / 100.0, 2);
   double lot3 = NormalizeDouble(totalLot - lot1 - lot2, 2);
   if(lot1 < MinLot) lot1 = MinLot;
   if(lot2 < MinLot) lot2 = MinLot;
   if(lot3 < MinLot) lot3 = MinLot;

   double tp1, tp2, tp3;
   if(type == ORDER_TYPE_BUY)
     {
      tp1 = price + slDist * TP1_RR;
      tp2 = price + slDist * TP2_RR;
      tp3 = price + slDist * TP3_RR;
     }
   else
     {
      tp1 = price - slDist * TP1_RR;
      tp2 = price - slDist * TP2_RR;
      tp3 = price - slDist * TP3_RR;
     }

   string dir = (type == ORDER_TYPE_BUY) ? "BUY" : "SELL";
   DBG("   باز کردن " + dir + " | total_lot=" + DoubleToString(totalLot,2) +
       " | SL_pips=" + DoubleToString(slPips,1) + " | risk=€" + DoubleToString(riskAmt,2));
   DBG("   TP1=" + DoubleToString(tp1,5) + " TP2=" + DoubleToString(tp2,5) + " TP3=" + DoubleToString(tp3,5));

   // ── سفارش TP1 ─────────────────────────────────────────────────
   Trade.PositionOpen(_Symbol, type, lot1, 0, sl, tp1,
      "PK_TP1|" + IntegerToString(Magic));
   uint ret1 = Trade.ResultRetcode();
   DBG("   OrderSend TP1 retcode=" + IntegerToString(ret1) +
       " | " + (ret1==TRADE_RETCODE_DONE ? "✅ موفق" : "❌ ناموفق: " + Trade.ResultRetcodeDescription()));

   // ── سفارش TP2 ─────────────────────────────────────────────────
   Trade.PositionOpen(_Symbol, type, lot2, 0, sl, tp2,
      "PK_TP2|" + IntegerToString(Magic));
   uint ret2 = Trade.ResultRetcode();
   DBG("   OrderSend TP2 retcode=" + IntegerToString(ret2) +
       " | " + (ret2==TRADE_RETCODE_DONE ? "✅ موفق" : "❌ ناموفق: " + Trade.ResultRetcodeDescription()));

   // ── سفارش TP3 ─────────────────────────────────────────────────
   Trade.PositionOpen(_Symbol, type, lot3, 0, sl, tp3,
      "PK_TP3|" + IntegerToString(Magic));
   uint ret3 = Trade.ResultRetcode();
   DBG("   OrderSend TP3 retcode=" + IntegerToString(ret3) +
       " | " + (ret3==TRADE_RETCODE_DONE ? "✅ موفق" : "❌ ناموفق: " + Trade.ResultRetcodeDescription()));

   if(ret1==TRADE_RETCODE_DONE || ret2==TRADE_RETCODE_DONE || ret3==TRADE_RETCODE_DONE)
     {
      TotalTrades += 3;
      LastAction = dir + " باز شد | lot=" + DoubleToString(totalLot,2);
      DBG("✅ معامله موفق: " + dir + " " + _Symbol);
     }
   else
      DBG("❌ تمام سفارش‌ها رد شدند");
  }

//══════════════════════════════════════════════════════════════════
//  ForceTestTrade — فقط Demo، 0.01 lot
//══════════════════════════════════════════════════════════════════
void RunForceTest()
  {
   if(AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_REAL)
     {
      DBG("⛔ ForceTestTrade: حساب Real — اجرا نشد");
      return;
     }

   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double atr_v[]; ArraySetAsSeries(atr_v, true);
   if(CopyBuffer(h_ATR, 0, 0, 2, atr_v) < 2) { DBG("❌ ForceTest: ATR خطا"); return; }

   double sl = bid - atr_v[1] * 2;
   double tp = bid + atr_v[1] * 2;

   DBG("🔬 ForceTestTrade: BUY 0.01 lot | ASK=" + DoubleToString(ask,5) +
       " | SL=" + DoubleToString(sl,5) + " | TP=" + DoubleToString(tp,5));

   Trade.PositionOpen(_Symbol, ORDER_TYPE_BUY, 0.01, ask, sl, tp,
      "PK_ForceTest|Demo");
   uint ret = Trade.ResultRetcode();
   DBG("🔬 ForceTest retcode=" + IntegerToString(ret) +
       " | " + (ret==TRADE_RETCODE_DONE ?
       "✅ موفق! اتصال به بروکر کار می‌کند" :
       "❌ ناموفق: " + Trade.ResultRetcodeDescription()));
  }

//══════════════════════════════════════════════════════════════════
//  مدیریت پوزیشن‌ها (Trailing Stop)
//══════════════════════════════════════════════════════════════════
void ManageOpenPositions()
  {
   for(int i = PositionsTotal()-1; i >= 0; i--)
     {
      if(!PosInfo.SelectByIndex(i)) continue;
      if(PosInfo.Magic()  != Magic)   continue;
      if(PosInfo.Symbol() != _Symbol) continue;

      double openPrice = PosInfo.PriceOpen();
      double curSL     = PosInfo.StopLoss();
      double curPrice  = PosInfo.PriceCurrent();

      if(PosInfo.PositionType() == POSITION_TYPE_BUY)
        {
         double profit_dist = curPrice - openPrice;
         if(profit_dist > MathAbs(openPrice - curSL) * 0.8 && curSL < openPrice)
           {
            double newSL = openPrice + _Point;
            if(newSL > curSL)
              {
               Trade.PositionModify(PosInfo.Ticket(), newSL, PosInfo.TakeProfit());
               if(DebugMode)
                  DBG("   Trailing: SL→Breakeven | ticket=" + IntegerToString(PosInfo.Ticket()));
              }
           }
        }
      else if(PosInfo.PositionType() == POSITION_TYPE_SELL)
        {
         double profit_dist = openPrice - curPrice;
         if(profit_dist > MathAbs(curSL - openPrice) * 0.8 && curSL > openPrice)
           {
            double newSL = openPrice - _Point;
            if(newSL < curSL)
              {
               Trade.PositionModify(PosInfo.Ticket(), newSL, PosInfo.TakeProfit());
               if(DebugMode)
                  DBG("   Trailing: SL→Breakeven | ticket=" + IntegerToString(PosInfo.Ticket()));
              }
           }
        }
     }
  }

//══════════════════════════════════════════════════════════════════
//  شمارش پوزیشن
//══════════════════════════════════════════════════════════════════
int CountMyPositions(ENUM_POSITION_TYPE type)
  {
   int count = 0;
   for(int i = 0; i < PositionsTotal(); i++)
      if(PosInfo.SelectByIndex(i))
         if(PosInfo.Magic()==Magic && PosInfo.Symbol()==_Symbol &&
            PosInfo.PositionType()==type) count++;
   return count;
  }

//══════════════════════════════════════════════════════════════════
//  لاگ با پرچم Debug
//══════════════════════════════════════════════════════════════════
void DBG(string msg)
  {
   if(DebugMode) Print("[Dragon FX Robot1] " + msg);
  }

//══════════════════════════════════════════════════════════════════
//  رسم پنل Dragon FX
//══════════════════════════════════════════════════════════════════
void DrawPanel()
  {
   int x = PanelX, y = PanelY;
   int w = 330, h = 400;

   // پس‌زمینه اصلی
   MakeRect("PK_BG",     x,   y,   w,   h,   C'10,12,25',  255);
   // هدر
   MakeRect("PK_HDR",    x,   y,   w,   55,  C'15,25,70',  255);
   // خطوط تزئینی هدر
   MakeRect("PK_HDR_L1", x,   y+53, w,   2,   C'40,80,200', 255);
   MakeRect("PK_HDR_L2", x,   y+55, w,   1,   C'20,40,100', 255);

   // DRAGON FX Logo
   MakeLbl("PK_LOGO1",   x+10, y+6,  "🐉 DRAGON FX",         clrDodgerBlue,  13, "Arial Bold");
   MakeLbl("PK_LOGO2",   x+10, y+26, "Robot 1  |  Pedram Kamangar", C'140,160,220', 9, "Arial");

   // بدنه پنل
   MakeLbl("PK_L_STATUS", x+12, y+68,  "وضعیت:",           C'150,160,180', 9);
   MakeLbl("PK_L_SYM",    x+12, y+88,  "جفت ارز:",         C'150,160,180', 9);
   MakeLbl("PK_L_TF",     x+12, y+108, "تایم‌فریم:",       C'150,160,180', 9);
   MakeLbl("PK_L_SIG",    x+12, y+128, "آخرین سیگنال:",   C'150,160,180', 9);
   MakeLbl("PK_L_RISK",   x+12, y+148, "ریسک هر معامله:", C'150,160,180', 9);

   MakeLbl("PK_V_STATUS", x+180, y+68,  "راه‌اندازی…",     clrYellow,  9);
   MakeLbl("PK_V_SYM",    x+180, y+88,  _Symbol,            clrWhite,   9);
   MakeLbl("PK_V_TF",     x+180, y+108, "Daily (D1)",       clrWhite,   9);
   MakeLbl("PK_V_SIG",    x+180, y+128, "---",              clrWhite,   9);
   MakeLbl("PK_V_RISK",   x+180, y+148, DoubleToString(RiskPercent,1)+"%", clrWhite, 9);

   MakeRect("PK_SEP1",    x, y+168, w, 1, C'30,40,80', 255);

   MakeLbl("PK_L_BAL",    x+12, y+178, "موجودی:",          C'150,160,180', 9);
   MakeLbl("PK_L_EQ",     x+12, y+198, "Equity:",          C'150,160,180', 9);
   MakeLbl("PK_L_PNL",    x+12, y+218, "سود/زیان باز:",   C'150,160,180', 9);
   MakeLbl("PK_L_POS",    x+12, y+238, "پوزیشن‌ها:",      C'150,160,180', 9);
   MakeLbl("PK_L_TOT",    x+12, y+258, "کل معاملات:",     C'150,160,180', 9);

   MakeLbl("PK_V_BAL",    x+180, y+178, "---",  clrWhite,   9);
   MakeLbl("PK_V_EQ",     x+180, y+198, "---",  clrWhite,   9);
   MakeLbl("PK_V_PNL",    x+180, y+218, "---",  clrYellow,  9);
   MakeLbl("PK_V_POS",    x+180, y+238, "---",  clrWhite,   9);
   MakeLbl("PK_V_TOT",    x+180, y+258, "---",  clrWhite,   9);

   MakeRect("PK_SEP2",    x, y+278, w, 1, C'30,40,80', 255);

   // وضعیت ربات — خط برجسته
   MakeRect("PK_STATUS_BG", x, y+283, w, 32, C'5,35,10', 255);
   MakeLbl("PK_ACTIVE",   x+12, y+291,
      "●  ربات در حال انجام وظیفه است",
      clrLimeGreen, 11, "Arial Bold");

   MakeRect("PK_SEP3",    x, y+318, w, 1, C'30,40,80', 255);

   // تنظیمات TP
   MakeLbl("PK_TP",       x+12, y+327,
      "TP1:" + DoubleToString(TP1_RR,1) + "R  TP2:" +
      DoubleToString(TP2_RR,1) + "R  TP3:" + DoubleToString(TP3_RR,1) + "R  |  ADX≥" +
      DoubleToString(ADX_MinLevel,0),
      C'80,100,160', 9);

   MakeRect("PK_SEP4",    x, y+347, w, 1, C'30,40,80', 255);

   // پاورقی
   MakeLbl("PK_FOOT1",    x+12, y+355,
      "© Pedram Kamangar — Dragon FX 2026",
      C'70,80,120', 8);
   MakeLbl("PK_FOOT2",    x+12, y+370,
      "SAR + Ichimoku + RSI Gate  |  v2.0",
      C'50,60,100', 8);

   // حالت Debug/ForceTest
   if(ForceTestTrade)
      MakeLbl("PK_FTEST", x+12, y+386, "⚠ ForceTestTrade ACTIVE", clrOrange, 8);

   ChartRedraw(0);
  }

//══════════════════════════════════════════════════════════════════
//  بروزرسانی پنل
//══════════════════════════════════════════════════════════════════
void UpdatePanel()
  {
   double balance  = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity   = AccountInfoDouble(ACCOUNT_EQUITY);
   double floatPnl = equity - balance;
   string currency = AccountInfoString(ACCOUNT_CURRENCY);

   int openBuy  = CountMyPositions(POSITION_TYPE_BUY);
   int openSell = CountMyPositions(POSITION_TYPE_SELL);
   int totalPos = openBuy + openSell;

   color pnlClr = (floatPnl >= 0) ? clrLimeGreen : clrOrangeRed;
   string statusTxt = IsActive ? "فعال ✓" : "آماده‌باش";
   color  statusClr = IsActive ? clrLimeGreen : clrYellow;
   string activeMsg = IsActive ?
      "●  ربات در حال انجام وظیفه است" :
      "○  در انتظار سیگنال";
   color activeClr  = IsActive ? clrLimeGreen : clrGray;

   UpdLbl("PK_V_STATUS", statusTxt, statusClr);
   UpdLbl("PK_V_SIG",    LastSignal, clrWhite);
   UpdLbl("PK_V_BAL",    DoubleToString(balance, 2) + " " + currency, clrWhite);
   UpdLbl("PK_V_EQ",     DoubleToString(equity,  2) + " " + currency, clrWhite);
   UpdLbl("PK_V_PNL",
      (floatPnl>=0 ? "+" : "") + DoubleToString(floatPnl,2) + " " + currency,
      pnlClr);
   UpdLbl("PK_V_POS",
      IntegerToString(totalPos) +
      " (B:" + IntegerToString(openBuy) +
      " S:"  + IntegerToString(openSell) + ")",
      clrWhite);
   UpdLbl("PK_V_TOT",    IntegerToString(TotalTrades), clrWhite);
   UpdLbl("PK_ACTIVE",   activeMsg, activeClr);

   ChartRedraw(0);
  }

//══════════════════════════════════════════════════════════════════
//  توابع کمکی رسم
//══════════════════════════════════════════════════════════════════
void MakeRect(string n, int x, int y, int w, int h, color c, uchar alpha)
  {
   ObjectCreate(0, n, OBJ_RECTANGLE_LABEL, 0, 0, 0);
   ObjectSetInteger(0, n, OBJPROP_XDISTANCE,   x);
   ObjectSetInteger(0, n, OBJPROP_YDISTANCE,   y);
   ObjectSetInteger(0, n, OBJPROP_XSIZE,       w);
   ObjectSetInteger(0, n, OBJPROP_YSIZE,       h);
   ObjectSetInteger(0, n, OBJPROP_BGCOLOR,     c);
   ObjectSetInteger(0, n, OBJPROP_BORDER_TYPE, BORDER_FLAT);
   ObjectSetInteger(0, n, OBJPROP_COLOR,       C'40,50,100');
   ObjectSetInteger(0, n, OBJPROP_CORNER,      CORNER_LEFT_UPPER);
   ObjectSetInteger(0, n, OBJPROP_BACK,        false);
   ObjectSetInteger(0, n, OBJPROP_SELECTABLE,  false);
   ObjectSetInteger(0, n, OBJPROP_ZORDER,      0);
  }

void MakeLbl(string n, int x, int y, string txt, color c,
             int sz=9, string font="Arial")
  {
   ObjectCreate(0, n, OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(0, n, OBJPROP_XDISTANCE,  x);
   ObjectSetInteger(0, n, OBJPROP_YDISTANCE,  y);
   ObjectSetString(0,  n, OBJPROP_TEXT,       txt);
   ObjectSetInteger(0, n, OBJPROP_COLOR,      c);
   ObjectSetInteger(0, n, OBJPROP_FONTSIZE,   sz);
   ObjectSetString(0,  n, OBJPROP_FONT,       font);
   ObjectSetInteger(0, n, OBJPROP_CORNER,     CORNER_LEFT_UPPER);
   ObjectSetInteger(0, n, OBJPROP_ANCHOR,     ANCHOR_LEFT_UPPER);
   ObjectSetInteger(0, n, OBJPROP_BACK,       false);
   ObjectSetInteger(0, n, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, n, OBJPROP_ZORDER,     1);
  }

void UpdLbl(string n, string txt, color c)
  {
   ObjectSetString(0,  n, OBJPROP_TEXT,  txt);
   ObjectSetInteger(0, n, OBJPROP_COLOR, c);
  }

//══════════════════════════════════════════════════════════════════
//  OnTradeTransaction
//══════════════════════════════════════════════════════════════════
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest     &req,
                        const MqlTradeResult      &res)
  {
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
     {
      double pnl = HistoryDealGetDouble(trans.deal, DEAL_PROFIT);
      if(pnl != 0)
        {
         TotalProfit += pnl;
         if(pnl > 0) WinTrades++;
         DBG((pnl>0 ? "✅ بسته شد سود: +" : "❌ بسته شد ضرر: ") +
             DoubleToString(pnl,2) + " | کل سود: " + DoubleToString(TotalProfit,2));
        }
     }
  }
//+------------------------------------------------------------------+
