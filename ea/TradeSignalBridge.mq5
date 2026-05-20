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
      trans_type, ticket, InpSymbol,
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
      "\"bid\":%s,"
      "\"ask\":%s"
      "}",
      now,
      InpSymbol,
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
   // ROM Fibonacci Pivot Points: PP = (prev_day_H + prev_day_L + prev_day_C) / 3
   // R/S levels extend from PP by (prev_day_range * ratio)
   double ph[1], pl[1], pc[1];
   if(CopyHigh(InpSymbol, PERIOD_D1, 1, 1, ph)  < 1 ||
      CopyLow(InpSymbol,  PERIOD_D1, 1, 1, pl)  < 1 ||
      CopyClose(InpSymbol, PERIOD_D1, 1, 1, pc) < 1)
   {
      Print("ComputeFibLevels: D1 data not ready");
      return;
   }

   double phigh = ph[0], plow = pl[0], pclose = pc[0];
   double range = phigh - plow;
   if(range <= 0) { Print("ComputeFibLevels: zero range"); return; }

   double PP = (phigh + plow + pclose) / 3.0;
   string direction = (pclose > (phigh + plow) / 2.0) ? "bullish" : "bearish";
   Print("ComputeFibLevels: PP=", F(PP), " H=", F(phigh), " L=", F(plow), " C=", F(pclose));

   // ROM ratios: 0.235, 0.382, 0.5, 0.618, 0.728, 1.0, 1.235, 1.328, 1.5, 1.618
   double ratios[] = {0.235, 0.382, 0.5, 0.618, 0.728, 1.0, 1.235, 1.328, 1.5, 1.618};
   string lbls[]   = {"0.235","0.382","0.5","0.618","0.728","1.000","1.235","1.328","1.500","1.618"};

   // levels includes PP (key "0.000") + R1..R10; extensions has S1..S10
   string lvl_json = StringFormat("\"0.000\":%s", F(PP));
   string ext_json = "";
   for(int i = 0; i < ArraySize(ratios); i++)
   {
      lvl_json += StringFormat(",\"%s\":%s", lbls[i], F(PP + range * ratios[i]));
      if(ext_json != "") ext_json += ",";
      ext_json += StringFormat("\"%s\":%s", lbls[i], F(PP - range * ratios[i]));
   }

   string body = StringFormat(
      "{\"symbol\":\"%s\",\"timeframe\":\"D1\","
      "\"swing_high\":%s,\"swing_low\":%s,\"direction\":\"%s\","
      "\"levels\":{%s},\"extensions\":{%s},\"computed_at\":\"%s\"}",
      InpSymbol, F(phigh), F(plow), direction,
      lvl_json, ext_json, ISOTime(TimeCurrent())
   );
   PostJSON("/api/fib-levels", body);
   DrawFibLines(PP, range, ratios, lbls);
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

void DrawFibLines(double PP, double range, double &ratios[], string &lbls[])
{
   for(int i = ObjectsTotal(0) - 1; i >= 0; i--)
   {
      string name = ObjectName(0, i);
      if(StringFind(name, "TSB_FIB_") == 0)
         ObjectDelete(0, name);
   }

   // PP center — gray dashed
   DrawFibLine("TSB_FIB_PP", PP, clrSilver, STYLE_DASH, 1, "ROM PP: " + F(PP));

   // R levels (above PP) — green
   for(int i = 0; i < ArraySize(ratios); i++)
      DrawFibLine("TSB_FIB_R_" + lbls[i], PP + range * ratios[i],
                  clrMediumSeaGreen, STYLE_SOLID, 1,
                  "ROM R" + lbls[i] + ": " + F(PP + range * ratios[i]));

   // S levels (below PP) — red
   for(int i = 0; i < ArraySize(ratios); i++)
      DrawFibLine("TSB_FIB_S_" + lbls[i], PP - range * ratios[i],
                  clrTomato, STYLE_SOLID, 1,
                  "ROM S" + lbls[i] + ": " + F(PP - range * ratios[i]));

   ChartRedraw(0);
}

void OnTimer()
{
   SendPriceTick();
   ComputeFibLevels();
}
