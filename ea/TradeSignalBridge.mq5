//+------------------------------------------------------------------+
//| TradeSignalBridge.mq5                                            |
//| Sends trade events and price bars to Trade Signal Partner API    |
//+------------------------------------------------------------------+
#property copyright "Trade Signal Partner"
#property version   "1.03"
#property strict

input string InpServerURL  = "http://127.0.0.1:8000";
input string InpSymbol     = "GOLD";
input int    InpTimerSec   = 60;
input int    InpMarketTickSec = 1;    // throttle bid/ask posts for paper exits
input int    InpSyncDays   = 30;   // days of closed deal history to sync on startup

datetime g_last_market_tick_sent = 0;
double   g_last_sent_swing_high  = 0.0;
double   g_last_sent_swing_low   = 0.0;

//--- HTTP POST — logs status code and response body on non-200
bool PostJSON(const string endpoint, const string body)
{
   string url     = InpServerURL + endpoint;
   string headers = "Content-Type: application/json\r\n";
   char   post[], result[];
   string result_headers;
   StringToCharArray(body, post, 0, StringLen(body));
   int res = WebRequest("POST", url, headers, 5000, post, result, result_headers);
   if(res == -1) {
      Print("WebRequest error: ", GetLastError(), " URL: ", url,
            " (Is Docker running? Is WebRequest allowed for ", InpServerURL, "?)");
      return false;
   }
   if(res < 200 || res >= 300) {
      string response = CharArrayToString(result);
      Print("API HTTP ", res, " on ", endpoint, " — ", response);
      return false;
   }
   return true;
}

//--- Health check — verifies API reachability
void CheckHealth()
{
   char   post[], result[];
   string result_headers;
   string url = InpServerURL + "/health";
   int res = WebRequest("GET", url, "", 5000, post, result, result_headers);
   if(res == -1)
      Print("Health check FAILED — cannot reach ", url,
            ". Error code: ", GetLastError(),
            ". Check: (1) Docker running? (2) WebRequest allowed for ", InpServerURL,
            " in Tools → Options → Expert Advisors.");
   else if(res == 200)
      Print("Health check OK — API reachable at ", url);
   else
      Print("Health check unexpected HTTP ", res, " from ", url);
}

//--- Sync all currently open positions for InpSymbol
void SyncOpenPositions()
{
   int total = PositionsTotal();
   if(total == 0) {
      Print("SyncOpenPositions: no open positions");
      return;
   }
   int synced = 0;
   for(int i = 0; i < total; i++) {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || PositionGetString(POSITION_SYMBOL) != InpSymbol) continue;

      ENUM_POSITION_TYPE pos_type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      string direction  = (pos_type == POSITION_TYPE_BUY) ? "buy" : "sell";
      double open_price = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl         = PositionGetDouble(POSITION_SL);
      double tp         = PositionGetDouble(POSITION_TP);
      double volume     = PositionGetDouble(POSITION_VOLUME);
      double profit     = PositionGetDouble(POSITION_PROFIT);
      double swap       = PositionGetDouble(POSITION_SWAP);
      datetime open_time = (datetime)PositionGetInteger(POSITION_TIME);

      string body = StringFormat(
         "{"
         "\"transaction_type\":\"DEAL_ADD\","
         "\"account_id\":%I64d,"
         "\"ticket\":%I64u,"
         "\"symbol\":\"%s\","
         "\"direction\":\"%s\","
         "\"order_type\":\"market\","
         "\"order_state\":\"filled\","
         "\"pending_price\":null,"
         "\"open_price\":%s,"
         "\"close_price\":null,"
         "\"volume\":%.2f,"
         "\"tp\":%s,"
         "\"sl\":%s,"
         "\"open_time\":\"%s\","
         "\"fill_time\":\"%s\","
         "\"close_time\":null,"
         "\"profit\":%.2f,"
         "\"swap\":%.2f,"
         "\"commission\":0.00"
         "}",
         AccountInfoInteger(ACCOUNT_LOGIN),
         ticket, InpSymbol, direction,
         F(open_price), volume,
         NullOrStr(tp), NullOrStr(sl),
         ISOTime(open_time), ISOTime(open_time),
         profit, swap
      );
      if(PostJSON("/api/trade-events", body)) synced++;
   }
   Print("SyncOpenPositions: synced ", synced, "/", total, " open positions for ", InpSymbol);
}

//--- Sync closed deal history for InpSymbol (last days_back days)
void SyncHistoryDeals(int days_back)
{
   datetime from = TimeCurrent() - (datetime)(days_back * 86400);
   if(!HistorySelect(from, TimeCurrent())) {
      Print("SyncHistoryDeals: HistorySelect failed");
      return;
   }
   int total = HistoryDealsTotal();
   if(total == 0) {
      Print("SyncHistoryDeals: no history in last ", days_back, " days");
      return;
   }
   int synced = 0;
   for(int i = 0; i < total; i++) {
      ulong deal_ticket = HistoryDealGetTicket(i);
      if(deal_ticket == 0) continue;
      if(HistoryDealGetString(deal_ticket, DEAL_SYMBOL) != InpSymbol) continue;

      long deal_entry = HistoryDealGetInteger(deal_ticket, DEAL_ENTRY);
      if(deal_entry != DEAL_ENTRY_IN && deal_entry != DEAL_ENTRY_OUT) continue;

      ENUM_DEAL_TYPE deal_type = (ENUM_DEAL_TYPE)HistoryDealGetInteger(deal_ticket, DEAL_TYPE);
      string direction  = (deal_type == DEAL_TYPE_BUY) ? "buy" : "sell";
      double deal_price = HistoryDealGetDouble(deal_ticket, DEAL_PRICE);
      double volume     = HistoryDealGetDouble(deal_ticket, DEAL_VOLUME);
      double profit     = HistoryDealGetDouble(deal_ticket, DEAL_PROFIT);
      double swap       = HistoryDealGetDouble(deal_ticket, DEAL_SWAP);
      double commission = HistoryDealGetDouble(deal_ticket, DEAL_COMMISSION);
      datetime deal_time = (datetime)HistoryDealGetInteger(deal_ticket, DEAL_TIME);

      // SL/TP live on the order, not the deal
      ulong order_ticket = (ulong)HistoryDealGetInteger(deal_ticket, DEAL_ORDER);
      double sl = 0, tp = 0;
      datetime open_time = deal_time;
      if(order_ticket > 0 && HistoryOrderSelect(order_ticket)) {
         sl        = HistoryOrderGetDouble(order_ticket, ORDER_SL);
         tp        = HistoryOrderGetDouble(order_ticket, ORDER_TP);
         open_time = (datetime)HistoryOrderGetInteger(order_ticket, ORDER_TIME_SETUP);
      }

      // Always use DEAL_POSITION_ID as canonical ticket so ENTRY_IN and ENTRY_OUT upsert onto the same row
      ulong position_id_in = (ulong)HistoryDealGetInteger(deal_ticket, DEAL_POSITION_ID);
      ulong canonical_ticket = (position_id_in > 0) ? position_id_in : deal_ticket;

      string body;
      if(deal_entry == DEAL_ENTRY_IN) {
         body = StringFormat(
            "{"
            "\"transaction_type\":\"DEAL_ADD\","
            "\"account_id\":%I64d,"
            "\"ticket\":%I64u,"
            "\"symbol\":\"%s\","
            "\"direction\":\"%s\","
            "\"order_type\":\"market\","
            "\"order_state\":\"filled\","
            "\"pending_price\":null,"
            "\"open_price\":%s,"
            "\"close_price\":null,"
            "\"volume\":%.2f,"
            "\"tp\":%s,"
            "\"sl\":%s,"
            "\"open_time\":\"%s\","
            "\"fill_time\":\"%s\","
            "\"close_time\":null,"
            "\"profit\":%.2f,"
            "\"swap\":%.2f,"
            "\"commission\":%.2f"
            "}",
            AccountInfoInteger(ACCOUNT_LOGIN),
            canonical_ticket, InpSymbol, direction,
            F(deal_price), volume,
            NullOrStr(tp), NullOrStr(sl),
            ISOTime(open_time), ISOTime(deal_time),
            profit, swap, commission
         );
      } else {
         // Use position ticket so this upserts onto the opening deal row (merges close data)
         ulong position_ticket = (ulong)HistoryDealGetInteger(deal_ticket, DEAL_POSITION_ID);
         ulong close_ticket = (position_ticket > 0) ? position_ticket : deal_ticket;
         body = StringFormat(
            "{"
            "\"transaction_type\":\"DEAL_ADD\","
            "\"account_id\":%I64d,"
            "\"ticket\":%I64u,"
            "\"symbol\":\"%s\","
            "\"direction\":\"%s\","
            "\"order_type\":\"market\","
            "\"order_state\":\"filled\","
            "\"pending_price\":null,"
            "\"open_price\":null,"
            "\"close_price\":%s,"
            "\"volume\":%.2f,"
            "\"tp\":%s,"
            "\"sl\":%s,"
            "\"open_time\":null,"
            "\"fill_time\":null,"
            "\"close_time\":\"%s\","
            "\"profit\":%.2f,"
            "\"swap\":%.2f,"
            "\"commission\":%.2f"
            "}",
            AccountInfoInteger(ACCOUNT_LOGIN),
            close_ticket, InpSymbol, direction,
            F(deal_price), volume,
            NullOrStr(tp), NullOrStr(sl),
            ISOTime(deal_time),
            profit, swap, commission
         );
      }
      if(PostJSON("/api/trade-events", body)) synced++;
   }
   Print("SyncHistoryDeals: synced ", synced, "/", total, " deals (last ", days_back, " days)");
}

//--- Format decimal safely
string F(double v)  { return DoubleToString(v, 5); }
string F2(double v) { return DoubleToString(v, 2); }

//--- Build OHLCV JSON for one timeframe
string BarJSON(ENUM_TIMEFRAMES tf)
{
   MqlRates rates[];
   if(CopyRates(InpSymbol, tf, 1, 1, rates) < 1) return "null";
   return StringFormat(
      "{\"open\":%.5f,\"high\":%.5f,\"low\":%.5f,\"close\":%.5f,\"volume\":%.0f}",
      rates[0].open, rates[0].high, rates[0].low, rates[0].close, (double)rates[0].tick_volume
   );
}

//--- Get timeframe string label
string TFLabel(ENUM_TIMEFRAMES tf)
{
   switch(tf) {
      case PERIOD_M5:  return "M5";
      case PERIOD_M15: return "M15";
      case PERIOD_M30: return "M30";
      case PERIOD_H1:  return "H1";
      case PERIOD_H4:  return "H4";
      case PERIOD_D1:  return "D";
      case PERIOD_W1:  return "W1";
      default:         return "UNKNOWN";
   }
}

//--- Direction string from order type
string DirectionStr(ENUM_ORDER_TYPE type)
{
   if(type == ORDER_TYPE_BUY || type == ORDER_TYPE_BUY_LIMIT ||
      type == ORDER_TYPE_BUY_STOP || type == ORDER_TYPE_BUY_STOP_LIMIT)
      return "buy";
   return "sell";
}

//--- OrderType string
string OrderTypeStr(ENUM_ORDER_TYPE type)
{
   switch(type) {
      case ORDER_TYPE_BUY:             return "market";
      case ORDER_TYPE_SELL:            return "market";
      case ORDER_TYPE_BUY_LIMIT:       return "buy_limit";
      case ORDER_TYPE_SELL_LIMIT:      return "sell_limit";
      case ORDER_TYPE_BUY_STOP:        return "buy_stop";
      case ORDER_TYPE_SELL_STOP:       return "sell_stop";
      case ORDER_TYPE_BUY_STOP_LIMIT:  return "buy_stop_limit";
      case ORDER_TYPE_SELL_STOP_LIMIT: return "sell_stop_limit";
      default:                         return "market";
   }
}

//--- ISO 8601 datetime
string ISOTime(datetime t)
{
   MqlDateTime dt;
   TimeToStruct(t, dt);
   return StringFormat("%04d-%02d-%02dT%02d:%02d:%02dZ",
      dt.year, dt.mon, dt.day, dt.hour, dt.min, dt.sec);
}

string NullOrStr(double v)    { return (v == 0.0) ? "null" : F(v); }
string NullOrTime(datetime t) { return (t == 0)   ? "null" : ("\"" + ISOTime(t) + "\""); }

int OnInit()
{
   // Tools → Options → Expert Advisors → Allow WebRequest for: http://127.0.0.1:8000
   EventSetTimer(InpTimerSec);
   Print("TradeSignalBridge v1.02 started. Sending to: ", InpServerURL, " | Symbol: ", InpSymbol);
   CheckHealth();
   SyncOpenPositions();
   SyncHistoryDeals(InpSyncDays);
   ComputeFibLevels();
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   // Remove all fib lines drawn by this EA
   for(int i = ObjectsTotal(0) - 1; i >= 0; i--)
   {
      string name = ObjectName(0, i);
      if(StringFind(name, "TSB_FIB_") == 0)
         ObjectDelete(0, name);
   }
   ChartRedraw(0);
   Print("TradeSignalBridge stopped.");
}

void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest    &request,
                        const MqlTradeResult     &result)
{
   if(trans.symbol != InpSymbol) {
      if(trans.type == TRADE_TRANSACTION_DEAL_ADD || trans.type == TRADE_TRANSACTION_ORDER_ADD)
         Print("Skipping transaction for symbol '", trans.symbol,
               "' (InpSymbol='", InpSymbol, "'). If this is your gold symbol, update InpSymbol.");
      return;
   }

   string trans_type  = "";
   string order_state = "filled";

   switch(trans.type) {
      case TRADE_TRANSACTION_ORDER_ADD:
         trans_type  = "ORDER_ADD";
         order_state = "pending";
         break;
      case TRADE_TRANSACTION_ORDER_UPDATE:
         trans_type  = "ORDER_UPDATE";
         order_state = "pending";
         break;
      case TRADE_TRANSACTION_ORDER_DELETE:
         trans_type  = "ORDER_DELETE";
         order_state = (trans.order_state == ORDER_STATE_CANCELED) ? "cancelled" : "expired";
         break;
      case TRADE_TRANSACTION_DEAL_ADD:
         trans_type  = "DEAL_ADD";
         order_state = "filled";
         break;
      default:
         return;
   }

   double open_price = 0, close_price = 0, volume = 0, tp = 0, sl = 0;
   double profit = 0, swap = 0, commission = 0, pending_price = 0;
   datetime open_time = 0, fill_time = 0, close_time = 0;
   ENUM_ORDER_TYPE order_type_enum = ORDER_TYPE_BUY;
   ulong ticket = trans.order;

   if(trans.type == TRADE_TRANSACTION_DEAL_ADD && trans.deal > 0) {
      if(HistoryDealSelect(trans.deal)) {
         // Always use DEAL_POSITION_ID as canonical ticket — both ENTRY_IN and ENTRY_OUT
         // upsert onto the same row regardless of whether deal_ticket == position_id
         ulong position_id = (ulong)HistoryDealGetInteger(trans.deal, DEAL_POSITION_ID);
         ticket      = (position_id > 0) ? position_id : (ulong)HistoryDealGetInteger(trans.deal, DEAL_TICKET);
         open_price  = HistoryDealGetDouble(trans.deal, DEAL_PRICE);
         volume      = HistoryDealGetDouble(trans.deal, DEAL_VOLUME);
         profit      = HistoryDealGetDouble(trans.deal, DEAL_PROFIT);
         swap        = HistoryDealGetDouble(trans.deal, DEAL_SWAP);
         commission  = HistoryDealGetDouble(trans.deal, DEAL_COMMISSION);
         fill_time   = (datetime)HistoryDealGetInteger(trans.deal, DEAL_TIME);
         long deal_entry = HistoryDealGetInteger(trans.deal, DEAL_ENTRY);
         if(deal_entry == DEAL_ENTRY_OUT || deal_entry == DEAL_ENTRY_INOUT) {
            close_price = open_price;
            close_time  = fill_time;
            open_price  = 0;
         }
      }
   }

   if(trans.order > 0 && HistoryOrderSelect(trans.order)) {
      if(open_price == 0) open_price = HistoryOrderGetDouble(trans.order, ORDER_PRICE_OPEN);
      tp              = HistoryOrderGetDouble(trans.order, ORDER_TP);
      sl              = HistoryOrderGetDouble(trans.order, ORDER_SL);
      pending_price   = HistoryOrderGetDouble(trans.order, ORDER_PRICE_CURRENT);
      open_time       = (datetime)HistoryOrderGetInteger(trans.order, ORDER_TIME_SETUP);
      order_type_enum = (ENUM_ORDER_TYPE)HistoryOrderGetInteger(trans.order, ORDER_TYPE);
      if(volume == 0) volume = HistoryOrderGetDouble(trans.order, ORDER_VOLUME_INITIAL);
   }

   string body = StringFormat(
      "{"
      "\"transaction_type\":\"%s\","
      "\"account_id\":%I64d,"
      "\"ticket\":%I64u,"
      "\"symbol\":\"%s\","
      "\"direction\":\"%s\","
      "\"order_type\":\"%s\","
      "\"order_state\":\"%s\","
      "\"pending_price\":%s,"
      "\"open_price\":%s,"
      "\"close_price\":%s,"
      "\"volume\":%.2f,"
      "\"tp\":%s,"
      "\"sl\":%s,"
      "\"open_time\":%s,"
      "\"fill_time\":%s,"
      "\"close_time\":%s,"
      "\"profit\":%.2f,"
      "\"swap\":%.2f,"
      "\"commission\":%.2f"
      "}",
      trans_type, AccountInfoInteger(ACCOUNT_LOGIN), ticket, InpSymbol,
      DirectionStr(order_type_enum),
      OrderTypeStr(order_type_enum),
      order_state,
      NullOrStr(pending_price),
      NullOrStr(open_price),
      NullOrStr(close_price),
      volume,
      NullOrStr(tp),
      NullOrStr(sl),
      NullOrTime(open_time),
      NullOrTime(fill_time),
      NullOrTime(close_time),
      profit, swap, commission
   );

   PostJSON("/api/trade-events", body);
}

void SendMarketTick()
{
   string now = "\"" + ISOTime(TimeCurrent()) + "\"";
   double bid = SymbolInfoDouble(InpSymbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(InpSymbol, SYMBOL_ASK);
   if(bid <= 0 || ask <= 0) return;

   string body = StringFormat(
      "{"
      "\"timestamp\":%s,"
      "\"symbol\":\"%s\","
      "\"account_id\":%I64d,"
      "\"bid\":%s,"
      "\"ask\":%s"
      "}",
      now,
      InpSymbol,
      AccountInfoInteger(ACCOUNT_LOGIN),
      F(bid),
      F(ask)
   );

   if(PostJSON("/api/market-tick", body))
      g_last_market_tick_sent = TimeCurrent();
}

void SendPriceTick()
{
   string now = "\"" + ISOTime(TimeCurrent()) + "\"";

   ENUM_TIMEFRAMES tfs[] = {PERIOD_M5, PERIOD_M15, PERIOD_M30, PERIOD_H1, PERIOD_H4, PERIOD_D1, PERIOD_W1};
   string bars_json = "";
   for(int i = 0; i < ArraySize(tfs); i++) {
      if(bars_json != "") bars_json += ",";
      bars_json += "\"" + TFLabel(tfs[i]) + "\":" + BarJSON(tfs[i]);
   }

   string body = StringFormat(
      "{"
      "\"timestamp\":%s,"
      "\"symbol\":\"%s\","
      "\"account_id\":%I64d,"
      "\"account\":{"
         "\"equity\":%.2f,"
         "\"balance\":%.2f,"
         "\"margin\":%.2f,"
         "\"free_margin\":%.2f,"
         "\"floating_pl\":%.2f"
      "},"
      "\"bars\":{%s}"
      "}",
      now,
      InpSymbol,
      AccountInfoInteger(ACCOUNT_LOGIN),
      AccountInfoDouble(ACCOUNT_EQUITY),
      AccountInfoDouble(ACCOUNT_BALANCE),
      AccountInfoDouble(ACCOUNT_MARGIN),
      AccountInfoDouble(ACCOUNT_MARGIN_FREE),
      AccountInfoDouble(ACCOUNT_EQUITY) - AccountInfoDouble(ACCOUNT_BALANCE),
      bars_json
   );

   PostJSON("/api/price-tick", body);
}

void OnTick()
{
   if(TimeCurrent() - g_last_market_tick_sent < InpMarketTickSec) return;
   SendMarketTick();
}

void ComputeFibLevels()
{
   MqlRates rates[];
   if(CopyRates(InpSymbol, PERIOD_D1, 0, 60, rates) < 60)
   {
      Print("ComputeFibLevels: D1 data not ready (less than 60 bars available)");
      return;
   }

   int pivot_high_idx = -1;
   int pivot_low_idx = -1;

   for(int i = 54; i >= 5; i--)
   {
      if(pivot_high_idx == -1)
      {
         bool is_pivot_high = true;
         for(int j = i - 5; j <= i + 5; j++)
         {
            if(j == i) continue;
            if(rates[i].high <= rates[j].high)
            {
               is_pivot_high = false;
               break;
            }
         }
         if(is_pivot_high)
         {
            pivot_high_idx = i;
         }
      }

      if(pivot_low_idx == -1)
      {
         bool is_pivot_low = true;
         for(int j = i - 5; j <= i + 5; j++)
         {
            if(j == i) continue;
            if(rates[i].low >= rates[j].low)
            {
               is_pivot_low = false;
               break;
            }
         }
         if(is_pivot_low)
         {
            pivot_low_idx = i;
         }
      }

      if(pivot_high_idx != -1 && pivot_low_idx != -1)
         break;
   }

   if(pivot_high_idx == -1 || pivot_low_idx == -1)
   {
      Print("ComputeFibLevels: pivot high/low not found in 60 bars");
      return;
   }

   double swing_high = rates[pivot_high_idx].high;
   double swing_low = rates[pivot_low_idx].low;
   double range = swing_high - swing_low;
   if(range <= 0)
   {
      Print("ComputeFibLevels: invalid range <= 0");
      return;
   }

   // direction: pivot_high_time > pivot_low_time ? "bearish" : "bullish"
   string direction = (rates[pivot_high_idx].time > rates[pivot_low_idx].time) ? "bearish" : "bullish";

   // Skip if swing levels have not changed
   if(swing_high == g_last_sent_swing_high && swing_low == g_last_sent_swing_low)
   {
      return;
   }

   double ratios[] = {0.236, 0.382, 0.5, 0.618, 0.786};
   string lbls[]   = {"0.236", "0.382", "0.500", "0.618", "0.786"};

   string lvl_json = "";
   string ext_json = "";
   for(int i = 0; i < ArraySize(ratios); i++)
   {
      if(lvl_json != "") lvl_json += ",";
      lvl_json += StringFormat("\"%s\":%s", lbls[i], F(swing_low + range * ratios[i]));

      if(ext_json != "") ext_json += ",";
      ext_json += StringFormat("\"%s\":%s", lbls[i], F(swing_low - range * ratios[i]));
   }

   string body = StringFormat(
      "{\"symbol\":\"%s\",\"timeframe\":\"D1\","
      "\"swing_high\":%s,\"swing_low\":%s,\"direction\":\"%s\","
      "\"levels\":{%s},\"extensions\":{%s},\"computed_at\":\"%s\"}",
      InpSymbol, F(swing_high), F(swing_low), direction,
      lvl_json, ext_json, ISOTime(TimeCurrent())
   );

   if(PostJSON("/api/fib-levels", body))
   {
      g_last_sent_swing_high = swing_high;
      g_last_sent_swing_low  = swing_low;
   }
   DrawFibLines(swing_high, swing_low, ratios, lbls);

}

void DrawFibLine(string name, double price, color clr, ENUM_LINE_STYLE style, int width, string tooltip)
{
   if(ObjectFind(0, name) >= 0)
      ObjectDelete(0, name);
   ObjectCreate(0, name, OBJ_HLINE, 0, 0, price);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_STYLE, style);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, width);
   ObjectSetString(0, name, OBJPROP_TOOLTIP, tooltip);
   ObjectSetInteger(0, name, OBJPROP_BACK, false);
}

void DrawFibLines(double swing_high, double swing_low, double &ratios[], string &lbls[])
{
   for(int i = ObjectsTotal(0) - 1; i >= 0; i--)
   {
      string name = ObjectName(0, i);
      if(StringFind(name, "TSB_FIB_") == 0)
         ObjectDelete(0, name);
   }

   double range = swing_high - swing_low;

   // Swing High line (Silver, dashed)
   DrawFibLine("TSB_FIB_HIGH", swing_high, clrSilver, STYLE_DASH, 1, "Swing High: " + F(swing_high));
   // Swing Low line (Silver, dashed)
   DrawFibLine("TSB_FIB_LOW", swing_low, clrSilver, STYLE_DASH, 1, "Swing Low: " + F(swing_low));

   // Retracements (above swing_low) - green
   for(int i = 0; i < ArraySize(ratios); i++)
   {
      double val = swing_low + range * ratios[i];
      DrawFibLine("TSB_FIB_RET_" + lbls[i], val, clrMediumSeaGreen, STYLE_SOLID, 1, "Retracement " + lbls[i] + ": " + F(val));
   }

   // Extensions (below swing_low) - red
   for(int i = 0; i < ArraySize(ratios); i++)
   {
      double val = swing_low - range * ratios[i];
      DrawFibLine("TSB_FIB_EXT_" + lbls[i], val, clrTomato, STYLE_SOLID, 1, "Extension " + lbls[i] + ": " + F(val));
   }

   ChartRedraw(0);
}

void OnTimer()
{
   SendPriceTick();
   ComputeFibLevels();
}
