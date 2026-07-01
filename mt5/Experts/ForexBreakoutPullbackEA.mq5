//+------------------------------------------------------------------+
//| ForexBreakoutPullbackEA.mq5                                      |
//| Research EA generated from the Python backtests in this repo.    |
//| Backtest and demo-test before any live use.                      |
//+------------------------------------------------------------------+
#property copyright "Research software - no profit guarantee"
#property version   "1.00"
#property strict

#include <Trade/Trade.mqh>

input ulong  InpMagicNumber        = 20260630;
input double InpRiskPercent        = 1.0;
input int    InpFastEma            = 8;
input int    InpSlowEma            = 55;
input int    InpRsiPeriod          = 14;
input int    InpAtrPeriod          = 21;
input int    InpAdxPeriod          = 21;
input int    InpSlopePeriod        = 20;
input int    InpBreakoutLookback   = 5;
input string InpSignalMode         = "pullback";
input int    InpMaxHoldBars        = 0;
input double InpPullbackAtr        = 0.45;
input double InpBreakoutAtr        = 0.03;
input double InpMinBodyAtr         = 0.10;
input double InpMinAdx             = 0.0;
input double InpMinSlopeAtr        = 0.0;
input double InpStopAtr            = 0.90;
input double InpTp1R               = 1.00;
input double InpTp2R               = 1.60;
input double InpTp3R               = 3.60;
input double InpTrailingAtr        = 1.60;
input double InpRsiLongMax         = 60.0;
input double InpRsiShortMin        = 45.0;
input int    InpSessionStartHour   = 7;
input int    InpSessionEndHour     = 17;
input double InpMaxSpreadPips      = 2.0;
input bool   InpAllowLong          = true;
input bool   InpAllowShort         = true;
input bool   InpShowChartPanel     = true;
input string InpOwnerName          = "pedram kamangar";
input string InpPanelStatusText    = "Robot is active and monitoring the strategy.";
input bool   InpEnableDiagnostics  = true;
input bool   ForceTestTrade        = false;

CTrade trade;
int fastEmaHandle;
int slowEmaHandle;
int rsiHandle;
int atrHandle;
int adxHandle;
datetime lastBarTime = 0;
string panelPrefix = "FBP_PANEL_";
bool forceTestTradeDone = false;

void Diag(const string message)
{
   if(InpEnableDiagnostics)
      Print("[FBP_DIAG] ", message);
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
   return StringFormat("FBP_%I64u_%s_%s", InpMagicNumber, _Symbol, suffix);
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

   long mode = AccountInfoInteger(ACCOUNT_TRADE_MODE);
   bool isDemo = mode == ACCOUNT_TRADE_MODE_DEMO;
   Diag(StringFormat("ForceTestTrade gate: enabled=yes account_mode=%s demo_required=%s", TradeModeText(), PassFail(isDemo)));
   if(!isDemo)
   {
      Diag("ForceTestTrade blocked: account is not DEMO. No diagnostic order will be sent.");
      forceTestTradeDone = true;
      return;
   }

   bool alreadyHasPosition = HasPosition();
   Diag(StringFormat("ForceTestTrade max-position gate: existing_position=%s", YesNo(alreadyHasPosition)));
   if(alreadyHasPosition)
      return;

   double requestedVolume = 0.01;
   double volume = NormalizeVolume(requestedVolume);
   if(volume <= 0.0 || MathAbs(volume - requestedVolume) > 0.0000001)
   {
      Diag(StringFormat(
         "ForceTestTrade blocked: broker volume rules do not allow exactly 0.01 lot. requested=%.2f normalized=%.2f min=%.2f step=%.2f",
         requestedVolume,
         volume,
         SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN),
         SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP)
      ));
      return;
   }

   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetDeviationInPoints(20);
   Diag(StringFormat("ForceTestTrade order attempt: yes side=BUY volume=%.2f symbol=%s", volume, _Symbol));
   bool sent = trade.Buy(volume, _Symbol, 0.0, 0.0, 0.0, "FBP ForceTestTrade demo diagnostic");
   Diag(StringFormat(
      "ForceTestTrade OrderSend result: sent=%s retcode=%u retcode_description=%s deal=%I64u order=%I64u",
      YesNo(sent),
      trade.ResultRetcode(),
      trade.ResultRetcodeDescription(),
      trade.ResultDeal(),
      trade.ResultOrder()
   ));
   if(sent)
   {
      forceTestTradeDone = true;
      Diag("ForceTestTrade disabled automatically after one successful DEMO diagnostic order.");
   }
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

void CreatePanelLabel(const string name, const int x, const int y, const string text, const color textColor, const int fontSize)
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

void CreatePanelBox(const string name, const int x, const int y, const int width, const int height, const color fillColor)
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
   ObjectSetInteger(0, objectName, OBJPROP_BORDER_TYPE, BORDER_FLAT);
   ObjectSetInteger(0, objectName, OBJPROP_COLOR, clrDimGray);
}

void DrawDragonLogo()
{
   CreatePanelLabel("dragon_head", 24, 17, "DRAGON", clrOrangeRed, 16);
   CreatePanelLabel("dragon_fx", 101, 20, "FX", clrDeepSkyBlue, 12);
   CreatePanelBox("scale_1", 23, 42, 26, 6, clrRed);
   CreatePanelBox("scale_2", 51, 42, 26, 6, clrOrange);
   CreatePanelBox("scale_3", 79, 42, 26, 6, clrGold);
   CreatePanelBox("scale_4", 107, 42, 26, 6, clrLimeGreen);
   CreatePanelBox("scale_5", 135, 42, 26, 6, clrDeepSkyBlue);
   CreatePanelBox("scale_6", 163, 42, 26, 6, clrMagenta);
}

void UpdateChartPanel()
{
   if(!InpShowChartPanel)
   {
      DeleteChartPanel();
      return;
   }

   string duty = HasPosition() ? "Strategy duty: managing an open trade." : "Strategy duty: scanning H4 breakout-pullback signals.";
   string tradeMode = TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) ? "Algo trading: terminal allowed" : "Algo trading: check MT5 permissions";
   double spreadPips = (SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID)) / PipSize();

   CreatePanelBox("background", 10, 10, 390, 138, clrBlack);
   CreatePanelBox("accent", 10, 10, 5, 138, clrOrangeRed);
   DrawDragonLogo();
   CreatePanelLabel("owner", 24, 56, "Owner: " + InpOwnerName, clrWhite, 10);
   CreatePanelLabel("status", 24, 76, InpPanelStatusText, clrPaleGreen, 10);
   CreatePanelLabel("duty", 24, 96, duty, clrLightSkyBlue, 10);
   CreatePanelLabel(
      "market",
      24,
      116,
      StringFormat("%s %s | risk %.2f%% | spread %.1f pips", _Symbol, EnumToString(_Period), InpRiskPercent, spreadPips),
      clrSilver,
      9
   );
   CreatePanelLabel("permission", 24, 132, tradeMode, clrSilver, 8);
   ChartRedraw(0);
}

void SavePositionState(const double entry, const double stopDistance, const bool isBuy, const double volume)
{
   double direction = isBuy ? 1.0 : -1.0;
   GlobalVariableSet(StateKey("entry"), entry);
   GlobalVariableSet(StateKey("risk"), stopDistance);
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
      Diag("Position management: no existing position for this symbol/magic.");
      return;
   }

   double atrValue;
   if(!CopyOne(atrHandle, 0, 1, atrValue))
   {
      Diag("Position management: ATR data unavailable, skipping management tick.");
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
      Diag(StringFormat("Position management: TP1 reached. partial_close_attempt=%s close_volume=%.2f", YesNo(closeVolume > 0.0 && closeVolume < volume), closeVolume));
      if(closeVolume > 0.0 && closeVolume < volume)
         trade.PositionClosePartial(_Symbol, closeVolume);
      Diag(StringFormat("PositionClosePartial TP1 retcode=%u description=%s", trade.ResultRetcode(), trade.ResultRetcodeDescription()));
      trade.PositionModify(_Symbol, openPrice, takeProfit);
      Diag(StringFormat("Breakeven modify after TP1 retcode=%u description=%s", trade.ResultRetcode(), trade.ResultRetcodeDescription()));
      GlobalVariableSet(StateKey("hit1"), 1.0);
      return;
   }

   if(hit2 < 0.5 && direction * (price - tp2) >= 0.0)
   {
      double closeVolume = NormalizeVolume(initialVolume / 3.0);
      Diag(StringFormat("Position management: TP2 reached. partial_close_attempt=%s close_volume=%.2f", YesNo(closeVolume > 0.0 && closeVolume < volume), closeVolume));
      if(closeVolume > 0.0 && closeVolume < volume)
         trade.PositionClosePartial(_Symbol, closeVolume);
      Diag(StringFormat("PositionClosePartial TP2 retcode=%u description=%s", trade.ResultRetcode(), trade.ResultRetcodeDescription()));
      GlobalVariableSet(StateKey("hit2"), 1.0);
      return;
   }

   if(direction * (price - tp3) >= 0.0)
   {
      Diag("Position management: TP3 reached, closing remaining position.");
      trade.PositionClose(_Symbol);
      Diag(StringFormat("PositionClose TP3 retcode=%u description=%s", trade.ResultRetcode(), trade.ResultRetcodeDescription()));
      return;
   }

   if(hit2 >= 0.5)
   {
      double trailDistance = InpTrailingAtr * atrValue;
      double newStop = isBuy ? price - trailDistance : price + trailDistance;
      bool shouldMove = (isBuy && newStop > stopLoss) || (!isBuy && (stopLoss == 0.0 || newStop < stopLoss));
      if(shouldMove)
      {
         Diag(StringFormat("Position management: trailing stop update attempt new_stop=%.5f old_stop=%.5f", newStop, stopLoss));
         trade.PositionModify(_Symbol, NormalizeDouble(newStop, _Digits), takeProfit);
         Diag(StringFormat("Trailing stop modify retcode=%u description=%s", trade.ResultRetcode(), trade.ResultRetcodeDescription()));
      }
   }

   if(InpMaxHoldBars > 0 && entryBarTime > 0)
   {
      int entryShift = iBarShift(_Symbol, _Period, entryBarTime, false);
      if(entryShift >= InpMaxHoldBars)
      {
         Diag(StringFormat("Position management: max-hold bars reached entry_shift=%d max_hold_bars=%d, closing position.", entryShift, InpMaxHoldBars));
         trade.PositionClose(_Symbol);
         Diag(StringFormat("PositionClose time-stop retcode=%u description=%s", trade.ResultRetcode(), trade.ResultRetcodeDescription()));
      }
   }
}

void EvaluateEntry()
{
   Diag("EvaluateEntry started.");

   bool existingPosition = HasPosition();
   Diag(StringFormat("Max positions check: %s existing_position=%s", PassFail(!existingPosition), YesNo(existingPosition)));
   if(existingPosition)
      return;

   int shift = 1;
   datetime barTime = iTime(_Symbol, _Period, shift);
   bool timeframeRecommended = _Period == PERIOD_H4;
   Diag(StringFormat(
      "Timeframe check: %s current=%s recommended=PERIOD_H4 blocking=no",
      PassFail(timeframeRecommended),
      EnumToString(_Period)
   ));

   bool sessionOk = InSession(barTime);
   Diag(StringFormat(
      "Session filter: %s bar_time=%s start_hour=%d end_hour=%d",
      PassFail(sessionOk),
      TimeToString(barTime, TIME_DATE | TIME_MINUTES),
      InpSessionStartHour,
      InpSessionEndHour
   ));
   if(!sessionOk)
      return;

   double spreadPips = (SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID)) / PipSize();
   bool spreadOk = spreadPips <= InpMaxSpreadPips;
   Diag(StringFormat("Spread filter: %s spread_pips=%.2f max_spread_pips=%.2f", PassFail(spreadOk), spreadPips, InpMaxSpreadPips));
   if(!spreadOk)
      return;

   Diag("News filter: PASSED no news filter is configured in this EA.");
   Diag("Cooldown timer: PASSED no cooldown timer is configured in this EA.");

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
   double previousClose = iClose(_Symbol, _Period, shift + 1);
   double slopeAtr = RollingSlope(shift) / MathMax(atrValue, _Point);
   double bodyAtr = MathAbs(close - open) / MathMax(atrValue, _Point);

   bool breakoutQuality = adxValue >= InpMinAdx && bodyAtr >= InpMinBodyAtr;
   bool uptrend = emaFast > emaSlow && close > emaSlow && slopeAtr > InpMinSlopeAtr;
   bool downtrend = emaFast < emaSlow && close < emaSlow && slopeAtr < -InpMinSlopeAtr;
   bool longPullback = low <= emaFast + InpPullbackAtr * atrValue;
   bool shortPullback = high >= emaFast - InpPullbackAtr * atrValue;
   bool longRecovery = prevRsi <= InpRsiLongMax && rsiValue > prevRsi;
   bool shortRecovery = prevRsi >= InpRsiShortMin && rsiValue < prevRsi;
   bool longBreak = close >= RecentHigh(shift) + InpBreakoutAtr * atrValue;
   bool shortBreak = close <= RecentLow(shift) - InpBreakoutAtr * atrValue;
   bool mildUptrend = emaFast >= emaSlow && slopeAtr >= -InpMinSlopeAtr;
   bool mildDowntrend = emaFast <= emaSlow && slopeAtr <= InpMinSlopeAtr;
   double candleRange = MathAbs(high - low);
   bool enoughRange = candleRange >= InpBreakoutAtr * atrValue;
   bool longSignal = false;
   bool shortSignal = false;

   Diag(StringFormat(
      "Trend check: uptrend=%s downtrend=%s mild_uptrend=%s mild_downtrend=%s ema_fast=%.5f ema_slow=%.5f close=%.5f slope_atr=%.5f min_slope_atr=%.5f",
      YesNo(uptrend),
      YesNo(downtrend),
      YesNo(mildUptrend),
      YesNo(mildDowntrend),
      emaFast,
      emaSlow,
      close,
      slopeAtr,
      InpMinSlopeAtr
   ));
   Diag(StringFormat(
      "ADX/body quality check: %s adx=%.2f min_adx=%.2f body_atr=%.4f min_body_atr=%.4f",
      PassFail(breakoutQuality),
      adxValue,
      InpMinAdx,
      bodyAtr,
      InpMinBodyAtr
   ));
   Diag(StringFormat(
      "RSI threshold check: rsi=%.2f previous_rsi=%.2f long_recovery=%s short_recovery=%s rsi_long_max=%.2f rsi_short_min=%.2f",
      rsiValue,
      prevRsi,
      YesNo(longRecovery),
      YesNo(shortRecovery),
      InpRsiLongMax,
      InpRsiShortMin
   ));
   Diag(StringFormat(
      "Breakout/pullback check: long_pullback=%s short_pullback=%s long_break=%s short_break=%s enough_range=%s breakout_lookback=%d breakout_atr=%.4f",
      YesNo(longPullback),
      YesNo(shortPullback),
      YesNo(longBreak),
      YesNo(shortBreak),
      YesNo(enoughRange),
      InpBreakoutLookback,
      InpBreakoutAtr
   ));

   if(InpSignalMode == "pullback")
   {
      longSignal = uptrend && longPullback && longRecovery && longBreak && breakoutQuality;
      shortSignal = downtrend && shortPullback && shortRecovery && shortBreak && breakoutQuality;
   }
   else if(InpSignalMode == "hf_momentum")
   {
      longSignal = mildUptrend && longRecovery && longBreak && breakoutQuality;
      shortSignal = mildDowntrend && shortRecovery && shortBreak && breakoutQuality;
   }
   else if(InpSignalMode == "hf_micro")
   {
      longSignal = mildUptrend && breakoutQuality && enoughRange && close > previousClose && close > emaFast && rsiValue >= InpRsiLongMax;
      shortSignal = mildDowntrend && breakoutQuality && enoughRange && close < previousClose && close < emaFast && rsiValue <= InpRsiShortMin;
   }
   else if(InpSignalMode == "hf_reversion")
   {
      double trendBuffer = InpPullbackAtr * atrValue;
      longSignal = close >= emaSlow - trendBuffer && low <= emaFast - InpPullbackAtr * atrValue && rsiValue <= InpRsiLongMax && close > open;
      shortSignal = close <= emaSlow + trendBuffer && high >= emaFast + InpPullbackAtr * atrValue && rsiValue >= InpRsiShortMin && close < open;
   }
   else
   {
      Print("Unsupported InpSignalMode: ", InpSignalMode);
      Diag(StringFormat("Signal generated: no unsupported_signal_mode=%s", InpSignalMode));
      return;
   }

   bool signalGenerated = longSignal || shortSignal;
   Diag(StringFormat(
      "Signal generated: %s mode=%s long_signal=%s short_signal=%s allow_long=%s allow_short=%s",
      YesNo(signalGenerated),
      InpSignalMode,
      YesNo(longSignal),
      YesNo(shortSignal),
      YesNo(InpAllowLong),
      YesNo(InpAllowShort)
   ));

   double stopDistance = InpStopAtr * atrValue;
   double volume = RiskVolume(stopDistance);
   bool volumeOk = volume > 0.0;
   Diag(StringFormat("Risk/volume check: %s stop_distance=%.5f atr=%.5f risk_percent=%.2f calculated_volume=%.2f", PassFail(volumeOk), stopDistance, atrValue, InpRiskPercent, volume));
   if(!volumeOk)
      return;

   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetDeviationInPoints(20);

   if(InpAllowLong && longSignal)
   {
      double entry = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double stopLoss = NormalizeDouble(entry - stopDistance, _Digits);
      Diag(StringFormat("Order attempt: yes side=BUY volume=%.2f entry=%.5f stop_loss=%.5f", volume, entry, stopLoss));
      bool sent = trade.Buy(volume, _Symbol, entry, stopLoss, 0.0, "FBP long");
      Diag(StringFormat(
         "OrderSend result: sent=%s retcode=%u retcode_description=%s deal=%I64u order=%I64u",
         YesNo(sent),
         trade.ResultRetcode(),
         trade.ResultRetcodeDescription(),
         trade.ResultDeal(),
         trade.ResultOrder()
      ));
      if(sent)
         SavePositionState(entry, stopDistance, true, volume);
   }
   else if(InpAllowShort && shortSignal)
   {
      double entry = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double stopLoss = NormalizeDouble(entry + stopDistance, _Digits);
      Diag(StringFormat("Order attempt: yes side=SELL volume=%.2f entry=%.5f stop_loss=%.5f", volume, entry, stopLoss));
      bool sent = trade.Sell(volume, _Symbol, entry, stopLoss, 0.0, "FBP short");
      Diag(StringFormat(
         "OrderSend result: sent=%s retcode=%u retcode_description=%s deal=%I64u order=%I64u",
         YesNo(sent),
         trade.ResultRetcode(),
         trade.ResultRetcodeDescription(),
         trade.ResultDeal(),
         trade.ResultOrder()
      ));
      if(sent)
         SavePositionState(entry, stopDistance, false, volume);
   }
   else
   {
      Diag(StringFormat(
         "Order attempt: no reason=no_enabled_signal long_signal=%s short_signal=%s allow_long=%s allow_short=%s",
         YesNo(longSignal),
         YesNo(shortSignal),
         YesNo(InpAllowLong),
         YesNo(InpAllowShort)
      ));
   }
}

int OnInit()
{
   Diag(StringFormat(
      "OnInit: symbol=%s timeframe=%s account_mode=%s force_test_trade=%s diagnostics=%s",
      _Symbol,
      EnumToString(_Period),
      TradeModeText(),
      YesNo(ForceTestTrade),
      YesNo(InpEnableDiagnostics)
   ));

   bool timeframeRecommended = _Period == PERIOD_H4;
   Diag(StringFormat("Timeframe check: %s current=%s recommended=PERIOD_H4 blocking=no", PassFail(timeframeRecommended), EnumToString(_Period)));
   if(_Period != PERIOD_H4)
      Print("Recommended timeframe is H4. Current timeframe: ", EnumToString(_Period));

   fastEmaHandle = iMA(_Symbol, _Period, InpFastEma, 0, MODE_EMA, PRICE_CLOSE);
   slowEmaHandle = iMA(_Symbol, _Period, InpSlowEma, 0, MODE_EMA, PRICE_CLOSE);
   rsiHandle = iRSI(_Symbol, _Period, InpRsiPeriod, PRICE_CLOSE);
   atrHandle = iATR(_Symbol, _Period, InpAtrPeriod);
   adxHandle = iADX(_Symbol, _Period, InpAdxPeriod);

   if(fastEmaHandle == INVALID_HANDLE || slowEmaHandle == INVALID_HANDLE ||
      rsiHandle == INVALID_HANDLE || atrHandle == INVALID_HANDLE || adxHandle == INVALID_HANDLE)
   {
      Print("Failed to create indicator handles.");
      Diag("OnInit failed: one or more indicator handles are INVALID_HANDLE.");
      return INIT_FAILED;
   }
   Diag("OnInit indicator handles: PASSED all handles created.");

   trade.SetExpertMagicNumber(InpMagicNumber);
   UpdateChartPanel();
   if(ForceTestTrade)
      Diag("ForceTestTrade is armed. It will attempt one 0.01 lot BUY only on a DEMO account after initialization.");
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
   Diag(StringFormat(
      "Tick received: symbol=%s timeframe=%s bid=%.5f ask=%.5f",
      _Symbol,
      EnumToString(_Period),
      SymbolInfoDouble(_Symbol, SYMBOL_BID),
      SymbolInfoDouble(_Symbol, SYMBOL_ASK)
   ));
   bool timeframeRecommended = _Period == PERIOD_H4;
   Diag(StringFormat("Timeframe check: %s current=%s recommended=PERIOD_H4 blocking=no", PassFail(timeframeRecommended), EnumToString(_Period)));

   ManageOpenPosition();
   UpdateChartPanel();
   TryForceTestTrade();

   datetime currentBarTime = iTime(_Symbol, _Period, 0);
   if(currentBarTime == lastBarTime)
   {
      Diag(StringFormat("New-bar gate: FAILED current_bar_time=%s last_bar_time=%s entry_evaluation=no", TimeToString(currentBarTime, TIME_DATE | TIME_MINUTES), TimeToString(lastBarTime, TIME_DATE | TIME_MINUTES)));
      return;
   }
   Diag(StringFormat("New-bar gate: PASSED current_bar_time=%s previous_bar_time=%s entry_evaluation=yes", TimeToString(currentBarTime, TIME_DATE | TIME_MINUTES), TimeToString(lastBarTime, TIME_DATE | TIME_MINUTES)));
   lastBarTime = currentBarTime;

   EvaluateEntry();
}
