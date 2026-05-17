//+------------------------------------------------------------------+
//| TradeSignalBridge.mq5                                            |
//| Sends trade events and price bars to Trade Signal Partner API    |
//+------------------------------------------------------------------+
#property copyright "Trade Signal Partner"
#property version   "1.00"
#property strict

input string InpServerURL  = "http://localhost:8000";
input string InpSymbol     = "XAUUSD";
input int    InpTimerSec   = 60;

//--- HTTP helper
bool PostJSON(const string endpoint, const string body)
{
   string url     = InpServerURL + endpoint;
   string headers = "Content-Type: application/json\r\n";
   char   post[], result[];
   string result_headers;
   StringToCharArray(body, post, 0, StringLen(body));
   int res = WebRequest("POST", url, headers, 5000, post, result, result_headers);
   if(res == -1) {
      Print("WebRequest error: ", GetLastError(), " URL: ", url);
      return false;
   }
   return true;
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
   // Tools → Options → Expert Advisors → Allow WebRequest for: http://localhost:8000
   EventSetTimer(InpTimerSec);
   Print("TradeSignalBridge v1.00 started. Sending to: ", InpServerURL);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   Print("TradeSignalBridge stopped.");
}

void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest    &request,
                        const MqlTradeResult     &result)
{
   if(trans.symbol != InpSymbol) return;

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
      case TRADE_TRANSACTION_POSITION_UPDATE:
         trans_type  = "POSITION_UPDATE";
         order_state = "filled";
         break;
      default:
         return;
   }

   double open_price = 0, close_price = 0, volume = 0, tp = 0, sl = 0;
   double profit = 0, swap = 0, commission = 0, pending_price = 0;
   datetime open_time = 0, fill_time = 0, close_time = 0;
   ENUM_ORDER_TYPE order_type_enum = ORDER_TYPE_BUY;
   long ticket = trans.order;

   if(trans.type == TRADE_TRANSACTION_DEAL_ADD && trans.deal > 0) {
      if(HistoryDealSelect(trans.deal)) {
         ticket      = (long)HistoryDealGetInteger(trans.deal, DEAL_TICKET);
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
      "\"ticket\":%I64d,"
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

void OnTimer()
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
      AccountInfoDouble(ACCOUNT_FREEMARGIN),
      AccountInfoDouble(ACCOUNT_EQUITY) - AccountInfoDouble(ACCOUNT_BALANCE),
      bars_json
   );

   PostJSON("/api/price-tick", body);
}
