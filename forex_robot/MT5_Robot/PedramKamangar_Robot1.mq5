//+------------------------------------------------------------------+
//|                    PEDRAM KAMANGAR — ROBOT 1                     |
//|              استراتژی: SAR + Ichimoku + RSI Gate                 |
//|         جفت ارز: EURUSD / GBPUSD  |  تایم‌فریم: Daily           |
//|                   نسخه: 1.0.0                                    |
//+------------------------------------------------------------------+
#property copyright   "Pedram Kamangar"
#property link        "https://github.com/pdekam2000"
#property version     "1.00"
#property description "Robot 1 — SAR+Ichimoku+RSI Gate Strategy"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Indicators\Trend.mqh>

//── ورودی‌ها ───────────────────────────────────────────────────────────────────
input group "═══════ مدیریت سرمایه ═══════"
input double RiskPercent    = 1.5;    // درصد ریسک هر معامله
input double MaxLot         = 2.0;    // حداکثر حجم (lot)
input double MinLot         = 0.01;   // حداقل حجم

input group "═══════ پارامترهای استراتژی ═══════"
input int    ADX_Period     = 14;     // دوره ADX
input double ADX_MinLevel   = 22.0;   // حداقل ADX برای ورود
input int    RSI_Period     = 14;     // دوره RSI
input double RSI_BuyMin     = 40.0;   // RSI خرید حداقل
input double RSI_BuyMax     = 68.0;   // RSI خرید حداکثر
input double RSI_SellMin    = 32.0;   // RSI فروش حداقل
input double RSI_SellMax    = 60.0;   // RSI فروش حداکثر
input double ATR_SL_Mult    = 1.3;    // ضریب ATR برای Stop Loss
input int    ATR_Period     = 14;     // دوره ATR

input group "═══════ Take Profit سه‌گانه ═══════"
input double TP1_RR         = 1.0;    // TP1 = 1× فاصله SL
input double TP2_RR         = 2.0;    // TP2 = 2× فاصله SL
input double TP3_RR         = 3.0;    // TP3 = 3× فاصله SL
input double TP1_Percent    = 33.0;   // درصد بسته‌شدن در TP1
input double TP2_Percent    = 33.0;   // درصد بسته‌شدن در TP2
// بقیه در TP3 بسته می‌شود

input group "═══════ Ichimoku ═══════"
input int    Ichi_Tenkan    = 9;
input int    Ichi_Kijun     = 26;
input int    Ichi_Senkou    = 52;

input group "═══════ Parabolic SAR ═══════"
input double SAR_Step       = 0.02;
input double SAR_Max        = 0.2;

input group "═══════ تنظیمات معاملاتی ═══════"
input int    Magic          = 20260001; // شناسه ربات
input int    Slippage       = 30;       // اسلیپیج (point)
input bool   EnableTrading  = true;     // معامله فعال؟

input group "═══════ نمایش پنل ═══════"
input bool   ShowPanel      = true;     // نمایش پنل
input color  PanelBgColor   = C'20,20,35';    // رنگ پس‌زمینه
input color  PanelTextColor = clrWhite;        // رنگ متن
input color  ProfitColor    = clrLimeGreen;    // رنگ سود
input color  LossColor      = clrOrangeRed;    // رنگ ضرر

//── متغیرهای کلی ───────────────────────────────────────────────────────────────
CTrade         Trade;
CPositionInfo  PosInfo;

// شناسه‌های اندیکاتور
int  h_SAR, h_Ichi, h_RSI, h_ADX, h_ATR;

// وضعیت
datetime LastBarTime   = 0;
int      TotalTrades   = 0;
double   TotalProfit   = 0.0;
int      WinTrades     = 0;
string   LastSignal    = "---";
string   LastAction    = "در انتظار سیگنال";
bool     IsActive      = false;

// لاگ
string   LogMessages[];
int      LogCount      = 0;

//+------------------------------------------------------------------+
//|  شروع ربات                                                        |
//+------------------------------------------------------------------+
int OnInit()
  {
   Trade.SetExpertMagicNumber(Magic);
   Trade.SetDeviationInPoints(Slippage);
   Trade.SetTypeFilling(ORDER_FILLING_IOC);

   // اندیکاتورها
   h_SAR  = iSAR(_Symbol, PERIOD_D1, SAR_Step, SAR_Max);
   h_Ichi = iIchimoku(_Symbol, PERIOD_D1, Ichi_Tenkan, Ichi_Kijun, Ichi_Senkou);
   h_RSI  = iRSI(_Symbol, PERIOD_D1, RSI_Period, PRICE_CLOSE);
   h_ADX  = iADX(_Symbol, PERIOD_D1, ADX_Period);
   h_ATR  = iATR(_Symbol, PERIOD_D1, ATR_Period);

   if(h_SAR == INVALID_HANDLE || h_Ichi == INVALID_HANDLE ||
      h_RSI == INVALID_HANDLE || h_ADX  == INVALID_HANDLE ||
      h_ATR == INVALID_HANDLE)
     {
      Print("خطا: اندیکاتورها بارگذاری نشدند!");
      return INIT_FAILED;
     }

   if(ShowPanel) DrawPanel();
   AddLog("ربات راه‌اندازی شد ✓");
   Print("=== Robot 1 | Pedram Kamangar | فعال شد ===");
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
//|  پاکسازی                                                          |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   IndicatorRelease(h_SAR);
   IndicatorRelease(h_Ichi);
   IndicatorRelease(h_RSI);
   IndicatorRelease(h_ADX);
   IndicatorRelease(h_ATR);
   ObjectsDeleteAll(0, "PK_");
   Comment("");
  }

//+------------------------------------------------------------------+
//|  هر تیک                                                           |
//+------------------------------------------------------------------+
void OnTick()
  {
   if(!EnableTrading) return;

   // فقط روی کندل جدید اجرا کن (Daily)
   datetime barTime = iTime(_Symbol, PERIOD_D1, 0);
   if(barTime == LastBarTime) 
     {
      if(ShowPanel) UpdatePanel();
      ManageOpenPositions();
      return;
     }
   LastBarTime = barTime;

   // بررسی سیگنال
   IsActive = true;
   CheckSignal();
   ManageOpenPositions();
   if(ShowPanel) UpdatePanel();
  }

//+------------------------------------------------------------------+
//|  بررسی سیگنال ورود                                               |
//+------------------------------------------------------------------+
void CheckSignal()
  {
   // دریافت مقادیر اندیکاتور (کندل قبلی = index 1)
   double sar[];       ArraySetAsSeries(sar, true);
   double tenkan[];    ArraySetAsSeries(tenkan, true);
   double kijun[];     ArraySetAsSeries(kijun, true);
   double senkouA[];   ArraySetAsSeries(senkouA, true);
   double senkouB[];   ArraySetAsSeries(senkouB, true);
   double rsi[];       ArraySetAsSeries(rsi, true);
   double adx[];       ArraySetAsSeries(adx, true);
   double atr[];       ArraySetAsSeries(atr, true);
   double close[];     ArraySetAsSeries(close, true);

   if(CopyBuffer(h_SAR,  0, 0, 3, sar)     < 3) return;
   if(CopyBuffer(h_Ichi, 0, 0, 3, tenkan)  < 3) return;
   if(CopyBuffer(h_Ichi, 1, 0, 3, kijun)   < 3) return;
   if(CopyBuffer(h_Ichi, 2, 0, 3, senkouA) < 3) return;
   if(CopyBuffer(h_Ichi, 3, 0, 3, senkouB) < 3) return;
   if(CopyBuffer(h_RSI,  0, 0, 3, rsi)     < 3) return;
   if(CopyBuffer(h_ADX,  0, 0, 3, adx)     < 3) return;
   if(CopyBuffer(h_ATR,  0, 0, 3, atr)     < 3) return;
   if(CopyClose(_Symbol, PERIOD_D1, 0, 3, close) < 3) return;

   double price = close[1];  // کلوز کندل قبلی
   double atrVal = atr[1];

   // ── شرط‌های مشترک ─────────────────────────────────────────────────────────
   bool adxOK   = adx[1] >= ADX_MinLevel;
   bool cloudTop = MathMax(senkouA[1], senkouB[1]);
   bool cloudBot = MathMin(senkouA[1], senkouB[1]);

   // SAR flip
   bool sarFlipUp = (sar[1] < close[1]) && (sar[2] > close[2]);
   bool sarFlipDn = (sar[1] > close[1]) && (sar[2] < close[2]);

   // ── سیگنال خرید ──────────────────────────────────────────────────────────
   bool buyCloud = close[1] > MathMax(senkouA[1], senkouB[1]);
   bool buyTK    = tenkan[1] > kijun[1];
   bool buyRSI   = rsi[1] >= RSI_BuyMin && rsi[1] <= RSI_BuyMax;

   if(sarFlipUp && buyCloud && buyTK && buyRSI && adxOK)
     {
      if(CountMyPositions(POSITION_TYPE_BUY) == 0)
        {
         LastSignal = "BUY ▲";
         double sl = price - atrVal * ATR_SL_Mult;
         OpenThreePartOrder(ORDER_TYPE_BUY, price, sl, atrVal);
        }
     }

   // ── سیگنال فروش ──────────────────────────────────────────────────────────
   bool sellCloud = close[1] < MathMin(senkouA[1], senkouB[1]);
   bool sellTK    = tenkan[1] < kijun[1];
   bool sellRSI   = rsi[1] >= RSI_SellMin && rsi[1] <= RSI_SellMax;

   if(sarFlipDn && sellCloud && sellTK && sellRSI && adxOK)
     {
      if(CountMyPositions(POSITION_TYPE_SELL) == 0)
        {
         LastSignal = "SELL ▼";
         double sl = price + atrVal * ATR_SL_Mult;
         OpenThreePartOrder(ORDER_TYPE_SELL, price, sl, atrVal);
        }
     }
  }

//+------------------------------------------------------------------+
//|  باز کردن ۳ پوزیشن برای سه سطح TP                               |
//+------------------------------------------------------------------+
void OpenThreePartOrder(ENUM_ORDER_TYPE type, double price, double sl, double atrVal)
  {
   double balance  = AccountInfoDouble(ACCOUNT_BALANCE);
   double slPips   = MathAbs(price - sl) / _Point / 10.0;
   if(slPips < 3) slPips = 10;

   double riskAmt  = balance * RiskPercent / 100.0;
   double pipVal   = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE) * 10;
   if(pipVal <= 0) pipVal = 10;

   double totalLot = NormalizeDouble(riskAmt / (slPips * pipVal), 2);
   totalLot = MathMax(MinLot * 3, MathMin(MaxLot, totalLot));

   double lot1 = NormalizeDouble(totalLot * TP1_Percent / 100.0, 2);
   double lot2 = NormalizeDouble(totalLot * TP2_Percent / 100.0, 2);
   double lot3 = NormalizeDouble(totalLot - lot1 - lot2, 2);
   if(lot1 < MinLot) lot1 = MinLot;
   if(lot2 < MinLot) lot2 = MinLot;
   if(lot3 < MinLot) lot3 = MinLot;

   double slDist = MathAbs(price - sl);
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

   // سفارش اول: TP1
   if(Trade.PositionOpen(_Symbol, type, lot1, 0, sl, tp1,
      "PK_Robot1_TP1|" + IntegerToString(Magic)))
      AddLog("✓ ورود TP1 | lot=" + DoubleToString(lot1, 2));

   // سفارش دوم: TP2
   if(Trade.PositionOpen(_Symbol, type, lot2, 0, sl, tp2,
      "PK_Robot1_TP2|" + IntegerToString(Magic)))
      AddLog("✓ ورود TP2 | lot=" + DoubleToString(lot2, 2));

   // سفارش سوم: TP3
   if(Trade.PositionOpen(_Symbol, type, lot3, 0, sl, tp3,
      "PK_Robot1_TP3|" + IntegerToString(Magic)))
      AddLog("✓ ورود TP3 | lot=" + DoubleToString(lot3, 2));

   LastAction = "معامله باز شد: " + (type == ORDER_TYPE_BUY ? "BUY" : "SELL");
   TotalTrades += 3;
  }

//+------------------------------------------------------------------+
//|  مدیریت پوزیشن‌های باز (Trailing Stop)                           |
//+------------------------------------------------------------------+
void ManageOpenPositions()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      if(!PosInfo.SelectByIndex(i)) continue;
      if(PosInfo.Magic()  != Magic)  continue;
      if(PosInfo.Symbol() != _Symbol) continue;

      // Trailing: بعد از اینکه قیمت از SL فاصله گرفت، SL را به breakeven برگردان
      double openPrice = PosInfo.PriceOpen();
      double curSL     = PosInfo.StopLoss();
      double curPrice  = PosInfo.PriceCurrent();
      double atr_now   = iATR(_Symbol, PERIOD_D1, ATR_Period);

      if(PosInfo.PositionType() == POSITION_TYPE_BUY)
        {
         double profit_dist = curPrice - openPrice;
         if(profit_dist > (openPrice - curSL) * 0.8 && curSL < openPrice)
           {
            // به breakeven برگردان
            double newSL = openPrice + _Point;
            if(newSL > curSL)
               Trade.PositionModify(PosInfo.Ticket(), newSL, PosInfo.TakeProfit());
           }
        }
      else if(PosInfo.PositionType() == POSITION_TYPE_SELL)
        {
         double profit_dist = openPrice - curPrice;
         if(profit_dist > (curSL - openPrice) * 0.8 && curSL > openPrice)
           {
            double newSL = openPrice - _Point;
            if(newSL < curSL)
               Trade.PositionModify(PosInfo.Ticket(), newSL, PosInfo.TakeProfit());
           }
        }
     }
  }

//+------------------------------------------------------------------+
//|  شمارش پوزیشن‌های باز                                            |
//+------------------------------------------------------------------+
int CountMyPositions(ENUM_POSITION_TYPE type)
  {
   int count = 0;
   for(int i = 0; i < PositionsTotal(); i++)
     {
      if(PosInfo.SelectByIndex(i))
        if(PosInfo.Magic()  == Magic &&
           PosInfo.Symbol() == _Symbol &&
           PosInfo.PositionType() == type)
           count++;
     }
   return count;
  }

//+------------------------------------------------------------------+
//|  افزودن لاگ                                                       |
//+------------------------------------------------------------------+
void AddLog(string msg)
  {
   string timeStr = TimeToString(TimeCurrent(), TIME_DATE|TIME_MINUTES);
   Print("[Robot1] " + timeStr + " | " + msg);
   ArrayResize(LogMessages, LogCount + 1);
   LogMessages[LogCount] = timeStr + " | " + msg;
   LogCount++;
   if(LogCount > 8) LogCount = 8;
  }

//+------------------------------------------------------------------+
//|  رسم پنل اصلی                                                     |
//+------------------------------------------------------------------+
void DrawPanel()
  {
   int x = 15, y = 15;
   int w = 320, h = 390;

   // پس‌زمینه پنل
   CreateRect("PK_BG", x, y, w, h, PanelBgColor, 200);
   CreateRect("PK_HEADER", x, y, w, 50, C'30,60,100', 255);

   // لوگوی گربه (ASCII art)
   string cat = " /\\_/\\  Pedram Kamangar";
   CreateLabel("PK_CAT",      x+10, y+8,  cat,        clrCyan,     12, "Courier New");
   CreateLabel("PK_SUBTITLE", x+10, y+28, "( o.o )  Robot 1 v1.0", clrLightBlue, 9, "Courier New");

   // خط جدا
   CreateHLine("PK_LINE1", x, y+55, w, clrDimGray);

   // اطلاعات اصلی
   CreateLabel("PK_LBL_STATUS", x+10, y+65,  "وضعیت:",         clrSilver,    9);
   CreateLabel("PK_LBL_SYM",    x+10, y+85,  "جفت ارز:",       clrSilver,    9);
   CreateLabel("PK_LBL_TF",     x+10, y+105, "تایم‌فریم:",     clrSilver,    9);
   CreateLabel("PK_LBL_SIG",    x+10, y+125, "آخرین سیگنال:", clrSilver,    9);
   CreateLabel("PK_LBL_RISK",   x+10, y+145, "ریسک هر معامله:", clrSilver,  9);
   CreateLabel("PK_LBL_ADX",    x+10, y+165, "حداقل ADX:",     clrSilver,    9);

   // مقادیر
   CreateLabel("PK_VAL_STATUS", x+170, y+65,  "در حال راه‌اندازی…", clrYellow, 9);
   CreateLabel("PK_VAL_SYM",    x+170, y+85,  _Symbol,             clrWhite,  9);
   CreateLabel("PK_VAL_TF",     x+170, y+105, "Daily (D1)",         clrWhite,  9);
   CreateLabel("PK_VAL_SIG",    x+170, y+125, "---",                clrWhite,  9);
   CreateLabel("PK_VAL_RISK",   x+170, y+145, DoubleToString(RiskPercent,1) + "%", clrWhite, 9);
   CreateLabel("PK_VAL_ADX",    x+170, y+165, DoubleToString(ADX_MinLevel,0), clrWhite, 9);

   // خط جدا
   CreateHLine("PK_LINE2", x, y+185, w, clrDimGray);

   // حساب
   CreateLabel("PK_LBL_BAL",   x+10, y+195, "موجودی:",         clrSilver, 9);
   CreateLabel("PK_LBL_EQ",    x+10, y+215, "Equity:",          clrSilver, 9);
   CreateLabel("PK_LBL_PNL",   x+10, y+235, "سود/زیان باز:",   clrSilver, 9);
   CreateLabel("PK_LBL_POS",   x+10, y+255, "پوزیشن‌های باز:", clrSilver, 9);
   CreateLabel("PK_LBL_TOTAL", x+10, y+275, "کل معاملات:",     clrSilver, 9);

   CreateLabel("PK_VAL_BAL",   x+170, y+195, "---", clrWhite,     9);
   CreateLabel("PK_VAL_EQ",    x+170, y+215, "---", clrWhite,     9);
   CreateLabel("PK_VAL_PNL",   x+170, y+235, "---", clrYellow,    9);
   CreateLabel("PK_VAL_POS",   x+170, y+255, "---", clrWhite,     9);
   CreateLabel("PK_VAL_TOTAL", x+170, y+275, "---", clrWhite,     9);

   // خط جدا
   CreateHLine("PK_LINE3", x, y+295, w, clrDimGray);

   // وضعیت ربات
   CreateLabel("PK_ROBOT_STATUS", x+10, y+305, "●  ربات در حال انجام وظیفه است", clrLimeGreen, 10, "Arial Bold");

   // TP سه‌گانه
   CreateLabel("PK_TP_INFO", x+10, y+325,
      "TP1:" + DoubleToString(TP1_RR,1) + "R  TP2:" + DoubleToString(TP2_RR,1) + "R  TP3:" + DoubleToString(TP3_RR,1) + "R",
      clrCadetBlue, 9);

   // پاورقی
   CreateHLine("PK_LINE4", x, y+345, w, clrDimGray);
   CreateLabel("PK_FOOTER", x+10, y+355,
      "© Pedram Kamangar — v1.0 — 2026",
      C'100,100,130', 8);
   CreateLabel("PK_COPY", x+10, y+370,
      "استراتژی: SAR + Ichimoku + RSI Gate",
      C'80,80,110', 8);

   ChartRedraw(0);
  }

//+------------------------------------------------------------------+
//|  بروزرسانی پنل                                                    |
//+------------------------------------------------------------------+
void UpdatePanel()
  {
   double balance  = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity   = AccountInfoDouble(ACCOUNT_EQUITY);
   double floatPnl = equity - balance;

   // وضعیت
   string statusText = IsActive ? "●  ربات در حال انجام وظیفه است" : "○  غیرفعال";
   color  statusClr  = IsActive ? clrLimeGreen : clrGray;

   int openBuy  = CountMyPositions(POSITION_TYPE_BUY);
   int openSell = CountMyPositions(POSITION_TYPE_SELL);
   int totalPos = openBuy + openSell;

   color pnlColor = floatPnl >= 0 ? ProfitColor : LossColor;

   UpdateLabel("PK_VAL_STATUS", IsActive ? "فعال ✓" : "آماده‌باش", IsActive ? clrLimeGreen : clrYellow);
   UpdateLabel("PK_VAL_SIG",    LastSignal,    clrWhite);
   UpdateLabel("PK_VAL_BAL",    DoubleToString(balance, 2) + " " + AccountInfoString(ACCOUNT_CURRENCY), clrWhite);
   UpdateLabel("PK_VAL_EQ",     DoubleToString(equity,  2) + " " + AccountInfoString(ACCOUNT_CURRENCY), clrWhite);
   UpdateLabel("PK_VAL_PNL",    (floatPnl >= 0 ? "+" : "") + DoubleToString(floatPnl, 2), pnlColor);
   UpdateLabel("PK_VAL_POS",    IntegerToString(totalPos) + " (B:" + IntegerToString(openBuy) + " S:" + IntegerToString(openSell) + ")", clrWhite);
   UpdateLabel("PK_VAL_TOTAL",  IntegerToString(TotalTrades), clrWhite);
   UpdateLabel("PK_ROBOT_STATUS", statusText, statusClr);

   ChartRedraw(0);
  }

//+------------------------------------------------------------------+
//|  توابع کمکی رسم                                                   |
//+------------------------------------------------------------------+
void CreateRect(string name, int x, int y, int w, int h, color clr, uchar alpha)
  {
   ObjectCreate(0, name, OBJ_RECTANGLE_LABEL, 0, 0, 0);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, name, OBJPROP_XSIZE, w);
   ObjectSetInteger(0, name, OBJPROP_YSIZE, h);
   ObjectSetInteger(0, name, OBJPROP_BGCOLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_BORDER_TYPE, BORDER_FLAT);
   ObjectSetInteger(0, name, OBJPROP_COLOR, C'60,60,80');
   ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, name, OBJPROP_BACK, false);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
  }

void CreateLabel(string name, int x, int y, string text, color clr,
                 int fontSize = 9, string fontName = "Arial")
  {
   ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE,  x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE,  y);
   ObjectSetString(0,  name, OBJPROP_TEXT,       text);
   ObjectSetInteger(0, name, OBJPROP_COLOR,      clr);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE,   fontSize);
   ObjectSetString(0,  name, OBJPROP_FONT,       fontName);
   ObjectSetInteger(0, name, OBJPROP_CORNER,     CORNER_LEFT_UPPER);
   ObjectSetInteger(0, name, OBJPROP_ANCHOR,     ANCHOR_LEFT_UPPER);
   ObjectSetInteger(0, name, OBJPROP_BACK,       false);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
  }

void CreateHLine(string name, int x, int y, int w, color clr)
  {
   ObjectCreate(0, name, OBJ_RECTANGLE_LABEL, 0, 0, 0);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, name, OBJPROP_XSIZE, w);
   ObjectSetInteger(0, name, OBJPROP_YSIZE, 1);
   ObjectSetInteger(0, name, OBJPROP_BGCOLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, name, OBJPROP_BACK, false);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
  }

void UpdateLabel(string name, string text, color clr)
  {
   ObjectSetString(0,  name, OBJPROP_TEXT,  text);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
  }

//+------------------------------------------------------------------+
//|  OnTradeTransaction — ثبت معاملات بسته‌شده                        |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest     &request,
                        const MqlTradeResult      &result)
  {
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
     {
      if(trans.deal_type == DEAL_TYPE_BUY || trans.deal_type == DEAL_TYPE_SELL)
        {
         double pnl = HistoryDealGetDouble(trans.deal, DEAL_PROFIT);
         if(pnl != 0)
           {
            TotalProfit += pnl;
            if(pnl > 0) WinTrades++;
            AddLog((pnl > 0 ? "✓ سود: +" : "✗ زیان: ") + DoubleToString(pnl, 2));
           }
        }
     }
  }
//+------------------------------------------------------------------+
