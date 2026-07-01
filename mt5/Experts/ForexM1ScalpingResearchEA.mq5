//+------------------------------------------------------------------+
//| ForexM1ScalpingResearchEA.mq5                                    |
//| Separate M1 scalping research EA. Demo/Strategy Tester only.      |
//+------------------------------------------------------------------+
#property copyright "Research software - no profit guarantee"
#property version   "1.00"
#property strict

#include <Trade/Trade.mqh>

input ulong  InpMagicNumber        = 20260701;
input double InpRiskPercent        = 0.5;
input int    InpFastEma            = 5;
input int    InpSlowEma            = 21;
input int    InpRsiPeriod          = 10;
input int    InpAtrPeriod          = 5;
input int    InpAdxPeriod          = 7;
input int    InpSlopePeriod        = 10;
input int    InpBreakoutLookback   = 2;
input string InpSignalMode         = "hf_momentum";
input int    InpMaxHoldBars        = 12;
input double InpBreakoutAtr        = 0.01;
input double InpMinBodyAtr         = 0.0;
input double InpMinAdx             = 10.0;
input double InpMinSlopeAtr        = 0.01;
input double InpStopAtr            = 3.2;
input double InpTp1R               = 0.35;
input double InpTp2R               = 0.4;
input double InpTp3R               = 2.2;
input double InpTrailingAtr        = 0.5;
input double InpRsiLongMax         = 55.0;
input double InpRsiShortMin        = 62.0;
input int    InpSessionStartHour   = 6;
input int    InpSessionEndHour     = 20;
input double InpMaxSpreadPips      = 0.5;
input bool   InpAllowLong          = true;
input bool   InpAllowShort         = true;
input bool   InpShowChartPanel     = true;
input string InpOwnerName          = "pedram kamangar";
input string InpPanelStatusText    = "M1 scalping research EA - demo testing only.";
input bool   InpEnableDiagnostics  = true;
input bool   ForceTestTrade        = false;

CTrade trade;
int fastEmaHandle;
int slowEmaHandle;
int rsiHandle;
int atrHandle;
int adxHandle;
datetime lastBarTime = 0;
string panelPrefix = "M1S_PANEL_";
bool forceTestTradeDone = false;

void Diag(const string message)
{
   if(InpEnableDiagnostics)
      Print("[M1_SCALP_DIAG] ", message);
}

string PassFail(const bool passed)
{
   return passed ? "PASSED" : "FAILED";
}

string YesNo(const bool value)
{
   return value ? "yes" : "no";
}

string TradeModeText()
{
   long mode = AccountInfoInteger(ACCOUNT_TRADE_MODE);
   if(mode == ACCOUNT_TRADE_MODE_DEMO)
      return "DEMO";
   if(mode == ACCOUNT_TRADE_MODE_CONTEST)
      return "CONTEST";
   if(mode == ACCOUNT_TRADE_MODE_REAL)
      return "REAL";
   return "UNKNOWN";
}

string StateKey(const string suffix)
{
   return StringFormat("M1S_%I64u_%s_%s", InpMagicNumber, _Symbol, suffix);
}

double PipSize()
{
   if(_Digits == 3 || _Digits == 5)
      return _Point * 10.0;
   return _Point;
}

bool CopyOne(const int handle, const int buffer, const int shift, double &value)
{
   double data[1];
   if(CopyBuffer(handle, buffer, shift, 1, data) != 1)
      return false;
   value = data[0];
   return true;
}

bool CopySeries(const int handle, const int buffer, const int shift, const int count, double &data[])
{
   ArrayResize(data, count);
   ArraySetAsSeries(data, true);
   return CopyBuffer(handle, buffer, shift, count, data) == count;
}

double RollingSlope(const int shift)
{
   double values[];
   if(!CopySeries(slowEmaHandle, 0, shift, InpSlopePeriod, values))
      return 0.0;

   double xMean = (InpSlopePeriod - 1) / 2.0;
   double yMean = 0.0;
   for(int i = 0; i < InpSlopePeriod; i++)
      yMean += values[InpSlopePeriod - 1 - i];
   yMean /= InpSlopePeriod;

   double numerator = 0.0;
   double denominator = 0.0;
   for(int i = 0; i < InpSlopePeriod; i++)
   {
      double x = i;
      double y = values[InpSlopePeriod - 1 - i];
      numerator += (x - xMean) * (y - yMean);
      denominator += (x - xMean) * (x - xMean);
   }
   if(denominator == 0.0)
      return 0.0;
   return numerator / denominator;
}

bool InSession(const datetime barTime)
{
   MqlDateTime parts;
   TimeToStruct(barTime, parts);
   int hour = parts.hour;
   if(InpSessionStartHour < InpSessionEndHour)
      return hour >= InpSessionStartHour && hour < InpSessionEndHour;
   return hour >= InpSessionStartHour || hour < InpSessionEndHour;
}

double RecentHigh(const int shift)
{
   double highest = iHigh(_Symbol, _Period, shift + 1);
   for(int i = shift + 1; i <= shift + InpBreakoutLookback; i++)
      highest = MathMax(highest, iHigh(_Symbol, _Period, i));
   return highest;
}

double RecentLow(const int shift)
{
   double lowest = iLow(_Symbol, _Period, shift + 1);
   for(int i = shift + 1; i <= shift + InpBreakoutLookback; i++)
      lowest = MathMin(lowest, iLow(_Symbol, _Period, i));
   return lowest;
}

double NormalizeVolume(const double volume)
{
   double minVolume = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxVolume = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double clipped = MathMax(minVolume, MathMin(maxVolume, volume));
   return MathFloor(clipped / step) * step;
}

double RiskVolume(const double stopDistance)
{
   if(stopDistance <= 0.0)
      return 0.0;

   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double riskMoney = equity * InpRiskPercent / 100.0;
   double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   if(tickSize <= 0.0 || tickValue <= 0.0)
      return 0.0;

   double lossPerLot = stopDistance / tickSize * tickValue;
   if(lossPerLot <= 0.0)
      return 0.0;
   return NormalizeVolume(riskMoney / lossPerLot);
}

bool HasPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol && PositionGetInteger(POSITION_MAGIC) == (long)InpMagicNumber)
         return true;
   }
   return false;
}

void TryForceTestTrade()
{
   if(!ForceTestTrade || forceTestTradeDone)
      return;

   bool isDemo = AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_DEMO;
   Diag(StringFormat("ForceTestTrade gate: account_mode=%s demo_required=%s", TradeModeText(), PassFail(isDemo)));
   if(!isDemo)
   {
      Diag("ForceTestTrade blocked: account is not DEMO.");
      forceTestTradeDone = true;
      return;
   }
   if(HasPosition())
   {
      Diag("ForceTestTrade blocked: existing position for this symbol/magic.");
      return;
   }

   double requestedVolume = 0.01;
   double volume = NormalizeVolume(requestedVolume);
   if(volume <= 0.0 || MathAbs(volume - requestedVolume) > 0.0000001)
   {
      Diag(StringFormat("ForceTestTrade blocked: exact 0.01 lot unavailable. normalized=%.2f", volume));
      return;
   }

   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetDeviationInPoints(20);
   Diag(StringFormat("ForceTestTrade order attempt: yes side=BUY volume=%.2f", volume));
   bool sent = trade.Buy(volume, _Symbol, 0.0, 0.0, 0.0, "M1 ForceTestTrade demo diagnostic");
   Diag(StringFormat(
      "ForceTestTrade OrderSend result: sent=%s retcode=%u retcode_description=%s deal=%I64u order=%I64u",
      YesNo(sent),
      trade.ResultRetcode(),
      trade.ResultRetcodeDescription(),
      trade.ResultDeal(),
      trade.ResultOrder()
   ));
   if(sent)
      forceTestTradeDone = true;
}

void DeleteChartPanel()
{
   int total = ObjectsTotal(0, 0, -1);
   for(int i = total - 1; i >= 0; i--)
   {
      string name = ObjectName(0, i, 0, -1);
      if(StringFind(name, panelPrefix) == 0)
         ObjectDelete(0, name);
   }
}

void PanelLabel(const string name, const int x, const int y, const string text, const color textColor, const int fontSize)
{
   string objectName = panelPrefix + name;
   if(ObjectFind(0, objectName) < 0)
      ObjectCreate(0, objectName, OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(0, objectName, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, objectName, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, objectName, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, objectName, OBJPROP_COLOR, textColor);
   ObjectSetInteger(0, objectName, OBJPROP_FONTSIZE, fontSize);
   ObjectSetString(0, objectName, OBJPROP_FONT, "Arial Bold");
   ObjectSetString(0, objectName, OBJPROP_TEXT, text);
}

void PanelBox(const string name, const int x, const int y, const int width, const int height, const color fillColor)
{
   string objectName = panelPrefix + name;
   if(ObjectFind(0, objectName) < 0)
      ObjectCreate(0, objectName, OBJ_RECTANGLE_LABEL, 0, 0, 0);
   ObjectSetInteger(0, objectName, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, objectName, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, objectName, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, objectName, OBJPROP_XSIZE, width);
   ObjectSetInteger(0, objectName, OBJPROP_YSIZE, height);
   ObjectSetInteger(0, objectName, OBJPROP_BGCOLOR, fillColor);
   ObjectSetInteger(0, objectName, OBJPROP_COLOR, clrDimGray);
}

void UpdateChartPanel()
{
   if(!InpShowChartPanel)
   {
      DeleteChartPanel();
      return;
   }

   double spreadPips = (SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID)) / PipSize();
   string duty = HasPosition() ? "M1 duty: managing open scalp trade." : "M1 duty: scanning scalping signals.";
   PanelBox("background", 10, 10, 410, 122, clrBlack);
   PanelBox("accent", 10, 10, 5, 122, clrDeepSkyBlue);
   PanelLabel("logo", 24, 18, "DRAGON FX M1 SCALPER", clrOrangeRed, 14);
   PanelLabel("owner", 24, 46, "Owner: " + InpOwnerName, clrWhite, 10);
   PanelLabel("status", 24, 66, InpPanelStatusText, clrPaleGreen, 10);
   PanelLabel("duty", 24, 86, duty, clrLightSkyBlue, 10);
   PanelLabel("market", 24, 106, StringFormat("%s %s | risk %.2f%% | spread %.1f pips", _Symbol, EnumToString(_Period), InpRiskPercent, spreadPips), clrSilver, 9);
   ChartRedraw(0);
}

void SavePositionState(const double entry, const double stopDistance, const bool isBuy, const double volume)
{
   double direction = isBuy ? 1.0 : -1.0;
   GlobalVariableSet(StateKey("tp1"), entry + direction * InpTp1R * stopDistance);
   GlobalVariableSet(StateKey("tp2"), entry + direction * InpTp2R * stopDistance);
   GlobalVariableSet(StateKey("tp3"), entry + direction * InpTp3R * stopDistance);
   GlobalVariableSet(StateKey("initial_volume"), volume);
   GlobalVariableSet(StateKey("hit1"), 0.0);
   GlobalVariableSet(StateKey("hit2"), 0.0);
   GlobalVariableSet(StateKey("entry_time"), (double)iTime(_Symbol, _Period, 0));
}

void ManageOpenPosition()
{
   if(!HasPosition())
   {
      Diag("Position management: no existing M1 position.");
      return;
   }

   double atrValue;
   if(!CopyOne(atrHandle, 0, 1, atrValue))
   {
      Diag("Position management: ATR unavailable.");
      return;
   }

   long type = PositionGetInteger(POSITION_TYPE);
   double volume = PositionGetDouble(POSITION_VOLUME);
   double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
   double stopLoss = PositionGetDouble(POSITION_SL);
   double takeProfit = PositionGetDouble(POSITION_TP);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   bool isBuy = type == POSITION_TYPE_BUY;
   double price = isBuy ? bid : ask;
   double direction = isBuy ? 1.0 : -1.0;
   double tp1 = GlobalVariableGet(StateKey("tp1"));
   double tp2 = GlobalVariableGet(StateKey("tp2"));
   double tp3 = GlobalVariableGet(StateKey("tp3"));
   double initialVolume = GlobalVariableGet(StateKey("initial_volume"));
   double hit1 = GlobalVariableGet(StateKey("hit1"));
   double hit2 = GlobalVariableGet(StateKey("hit2"));
   datetime entryBarTime = (datetime)GlobalVariableGet(StateKey("entry_time"));

   if(hit1 < 0.5 && direction * (price - tp1) >= 0.0)
   {
      double closeVolume = NormalizeVolume(initialVolume / 3.0);
      Diag(StringFormat("TP1 reached. partial close attempt volume=%.2f", closeVolume));
      if(closeVolume > 0.0 && closeVolume < volume)
         trade.PositionClosePartial(_Symbol, closeVolume);
      Diag(StringFormat("TP1 partial retcode=%u %s", trade.ResultRetcode(), trade.ResultRetcodeDescription()));
      trade.PositionModify(_Symbol, openPrice, takeProfit);
      Diag(StringFormat("Breakeven modify retcode=%u %s", trade.ResultRetcode(), trade.ResultRetcodeDescription()));
      GlobalVariableSet(StateKey("hit1"), 1.0);
      return;
   }

   if(hit2 < 0.5 && direction * (price - tp2) >= 0.0)
   {
      double closeVolume = NormalizeVolume(initialVolume / 3.0);
      Diag(StringFormat("TP2 reached. partial close attempt volume=%.2f", closeVolume));
      if(closeVolume > 0.0 && closeVolume < volume)
         trade.PositionClosePartial(_Symbol, closeVolume);
      Diag(StringFormat("TP2 partial retcode=%u %s", trade.ResultRetcode(), trade.ResultRetcodeDescription()));
      GlobalVariableSet(StateKey("hit2"), 1.0);
      return;
   }

   if(direction * (price - tp3) >= 0.0)
   {
      Diag("TP3 reached. Closing remaining M1 position.");
      trade.PositionClose(_Symbol);
      Diag(StringFormat("TP3 close retcode=%u %s", trade.ResultRetcode(), trade.ResultRetcodeDescription()));
      return;
   }

   if(hit2 >= 0.5)
   {
      double trailDistance = InpTrailingAtr * atrValue;
      double newStop = isBuy ? price - trailDistance : price + trailDistance;
      bool shouldMove = (isBuy && newStop > stopLoss) || (!isBuy && (stopLoss == 0.0 || newStop < stopLoss));
      if(shouldMove)
      {
         Diag(StringFormat("Trailing stop update attempt new_stop=%.5f", newStop));
         trade.PositionModify(_Symbol, NormalizeDouble(newStop, _Digits), takeProfit);
         Diag(StringFormat("Trailing retcode=%u %s", trade.ResultRetcode(), trade.ResultRetcodeDescription()));
      }
   }

   if(InpMaxHoldBars > 0 && entryBarTime > 0)
   {
      int entryShift = iBarShift(_Symbol, _Period, entryBarTime, false);
      if(entryShift >= InpMaxHoldBars)
      {
         Diag(StringFormat("Max hold bars reached: %d >= %d. Closing M1 scalp.", entryShift, InpMaxHoldBars));
         trade.PositionClose(_Symbol);
         Diag(StringFormat("Time-stop close retcode=%u %s", trade.ResultRetcode(), trade.ResultRetcodeDescription()));
      }
   }
}

void EvaluateEntry()
{
   Diag("EvaluateEntry started for M1 scalping EA.");
   bool existingPosition = HasPosition();
   Diag(StringFormat("Max positions check: %s existing_position=%s", PassFail(!existingPosition), YesNo(existingPosition)));
   if(existingPosition)
      return;

   int shift = 1;
   datetime barTime = iTime(_Symbol, _Period, shift);
   bool timeframeOk = _Period == PERIOD_M1;
   Diag(StringFormat("Timeframe check: %s current=%s required=PERIOD_M1 blocking=no", PassFail(timeframeOk), EnumToString(_Period)));

   bool sessionOk = InSession(barTime);
   Diag(StringFormat("Session filter: %s bar_time=%s start=%d end=%d", PassFail(sessionOk), TimeToString(barTime, TIME_DATE | TIME_MINUTES), InpSessionStartHour, InpSessionEndHour));
   if(!sessionOk)
      return;

   double spreadPips = (SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID)) / PipSize();
   bool spreadOk = spreadPips <= InpMaxSpreadPips;
   Diag(StringFormat("Spread filter: %s spread=%.2f max=%.2f", PassFail(spreadOk), spreadPips, InpMaxSpreadPips));
   if(!spreadOk)
      return;

   Diag("News filter: PASSED no news filter is configured.");
   Diag("Cooldown timer: PASSED no cooldown timer is configured.");

   double emaFast, emaSlow, rsiValue, prevRsi, atrValue, adxValue;
   bool indicatorsReady =
      CopyOne(fastEmaHandle, 0, shift, emaFast) &&
      CopyOne(slowEmaHandle, 0, shift, emaSlow) &&
      CopyOne(rsiHandle, 0, shift, rsiValue) &&
      CopyOne(rsiHandle, 0, shift + 1, prevRsi) &&
      CopyOne(atrHandle, 0, shift, atrValue) &&
      CopyOne(adxHandle, 0, shift, adxValue);
   Diag(StringFormat("Indicator data check: %s", PassFail(indicatorsReady)));
   if(!indicatorsReady)
      return;

   double open = iOpen(_Symbol, _Period, shift);
   double high = iHigh(_Symbol, _Period, shift);
   double low = iLow(_Symbol, _Period, shift);
   double close = iClose(_Symbol, _Period, shift);
   double slopeAtr = RollingSlope(shift) / MathMax(atrValue, _Point);
   double bodyAtr = MathAbs(close - open) / MathMax(atrValue, _Point);
   bool breakoutQuality = adxValue >= InpMinAdx && bodyAtr >= InpMinBodyAtr;
   bool mildUptrend = emaFast >= emaSlow && slopeAtr >= -InpMinSlopeAtr;
   bool mildDowntrend = emaFast <= emaSlow && slopeAtr <= InpMinSlopeAtr;
   bool longRecovery = prevRsi <= InpRsiLongMax && rsiValue > prevRsi;
   bool shortRecovery = prevRsi >= InpRsiShortMin && rsiValue < prevRsi;
   bool longBreak = close >= RecentHigh(shift) + InpBreakoutAtr * atrValue;
   bool shortBreak = close <= RecentLow(shift) - InpBreakoutAtr * atrValue;

   Diag(StringFormat("Trend check: mild_uptrend=%s mild_downtrend=%s ema_fast=%.5f ema_slow=%.5f slope_atr=%.5f", YesNo(mildUptrend), YesNo(mildDowntrend), emaFast, emaSlow, slopeAtr));
   Diag(StringFormat("ADX/body quality check: %s adx=%.2f min_adx=%.2f body_atr=%.4f", PassFail(breakoutQuality), adxValue, InpMinAdx, bodyAtr));
   Diag(StringFormat("RSI threshold check: rsi=%.2f prev=%.2f long_recovery=%s short_recovery=%s", rsiValue, prevRsi, YesNo(longRecovery), YesNo(shortRecovery)));
   Diag(StringFormat("Breakout check: long_break=%s short_break=%s lookback=%d breakout_atr=%.4f", YesNo(longBreak), YesNo(shortBreak), InpBreakoutLookback, InpBreakoutAtr));

   bool longSignal = mildUptrend && longRecovery && longBreak && breakoutQuality;
   bool shortSignal = mildDowntrend && shortRecovery && shortBreak && breakoutQuality;
   Diag(StringFormat("Signal generated: %s mode=hf_momentum long=%s short=%s", YesNo(longSignal || shortSignal), YesNo(longSignal), YesNo(shortSignal)));

   double stopDistance = InpStopAtr * atrValue;
   double volume = RiskVolume(stopDistance);
   bool volumeOk = volume > 0.0;
   Diag(StringFormat("Risk/volume check: %s stop_distance=%.5f calculated_volume=%.2f", PassFail(volumeOk), stopDistance, volume));
   if(!volumeOk)
      return;

   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetDeviationInPoints(20);
   if(InpAllowLong && longSignal)
   {
      double entry = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double stopLoss = NormalizeDouble(entry - stopDistance, _Digits);
      Diag(StringFormat("Order attempt: yes side=BUY volume=%.2f entry=%.5f sl=%.5f", volume, entry, stopLoss));
      bool sent = trade.Buy(volume, _Symbol, entry, stopLoss, 0.0, "M1 scalp long");
      Diag(StringFormat("OrderSend result: sent=%s retcode=%u description=%s deal=%I64u order=%I64u", YesNo(sent), trade.ResultRetcode(), trade.ResultRetcodeDescription(), trade.ResultDeal(), trade.ResultOrder()));
      if(sent)
         SavePositionState(entry, stopDistance, true, volume);
   }
   else if(InpAllowShort && shortSignal)
   {
      double entry = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double stopLoss = NormalizeDouble(entry + stopDistance, _Digits);
      Diag(StringFormat("Order attempt: yes side=SELL volume=%.2f entry=%.5f sl=%.5f", volume, entry, stopLoss));
      bool sent = trade.Sell(volume, _Symbol, entry, stopLoss, 0.0, "M1 scalp short");
      Diag(StringFormat("OrderSend result: sent=%s retcode=%u description=%s deal=%I64u order=%I64u", YesNo(sent), trade.ResultRetcode(), trade.ResultRetcodeDescription(), trade.ResultDeal(), trade.ResultOrder()));
      if(sent)
         SavePositionState(entry, stopDistance, false, volume);
   }
   else
   {
      Diag(StringFormat("Order attempt: no reason=no_enabled_signal long=%s short=%s allow_long=%s allow_short=%s", YesNo(longSignal), YesNo(shortSignal), YesNo(InpAllowLong), YesNo(InpAllowShort)));
   }
}

int OnInit()
{
   Diag(StringFormat("OnInit: M1 scalping EA symbol=%s timeframe=%s account=%s", _Symbol, EnumToString(_Period), TradeModeText()));
   bool timeframeOk = _Period == PERIOD_M1;
   Diag(StringFormat("Timeframe check: %s current=%s required=PERIOD_M1 blocking=no", PassFail(timeframeOk), EnumToString(_Period)));
   if(_Period != PERIOD_M1)
      Print("Recommended timeframe for ForexM1ScalpingResearchEA is M1. Current timeframe: ", EnumToString(_Period));

   fastEmaHandle = iMA(_Symbol, _Period, InpFastEma, 0, MODE_EMA, PRICE_CLOSE);
   slowEmaHandle = iMA(_Symbol, _Period, InpSlowEma, 0, MODE_EMA, PRICE_CLOSE);
   rsiHandle = iRSI(_Symbol, _Period, InpRsiPeriod, PRICE_CLOSE);
   atrHandle = iATR(_Symbol, _Period, InpAtrPeriod);
   adxHandle = iADX(_Symbol, _Period, InpAdxPeriod);
   if(fastEmaHandle == INVALID_HANDLE || slowEmaHandle == INVALID_HANDLE ||
      rsiHandle == INVALID_HANDLE || atrHandle == INVALID_HANDLE || adxHandle == INVALID_HANDLE)
   {
      Print("Failed to create M1 scalping indicator handles.");
      return INIT_FAILED;
   }

   trade.SetExpertMagicNumber(InpMagicNumber);
   UpdateChartPanel();
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   DeleteChartPanel();
   IndicatorRelease(fastEmaHandle);
   IndicatorRelease(slowEmaHandle);
   IndicatorRelease(rsiHandle);
   IndicatorRelease(atrHandle);
   IndicatorRelease(adxHandle);
}

void OnTick()
{
   Diag(StringFormat("Tick received: M1 EA symbol=%s timeframe=%s bid=%.5f ask=%.5f", _Symbol, EnumToString(_Period), SymbolInfoDouble(_Symbol, SYMBOL_BID), SymbolInfoDouble(_Symbol, SYMBOL_ASK)));
   Diag(StringFormat("Timeframe check: %s current=%s required=PERIOD_M1 blocking=no", PassFail(_Period == PERIOD_M1), EnumToString(_Period)));
   ManageOpenPosition();
   UpdateChartPanel();
   TryForceTestTrade();

   datetime currentBarTime = iTime(_Symbol, _Period, 0);
   if(currentBarTime == lastBarTime)
   {
      Diag(StringFormat("New-bar gate: FAILED current=%s last=%s", TimeToString(currentBarTime, TIME_DATE | TIME_MINUTES), TimeToString(lastBarTime, TIME_DATE | TIME_MINUTES)));
      return;
   }
   Diag(StringFormat("New-bar gate: PASSED current=%s previous=%s", TimeToString(currentBarTime, TIME_DATE | TIME_MINUTES), TimeToString(lastBarTime, TIME_DATE | TIME_MINUTES)));
   lastBarTime = currentBarTime;
   EvaluateEntry();
}
