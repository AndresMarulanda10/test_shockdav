from scripts.real_extract_full import fetch_market_symbols, probe_symbol_for_orders, API_KEY, SECRET_KEY, PASSPHRASE
import time

if __name__ == '__main__':
    cap = 10
    probes_cap = 24
    symbols = fetch_market_symbols(cap=cap)
    print(f"Running probe sweep on {len(symbols)} symbols (cap {cap}), probes_per_symbol={probes_cap}\nSymbols: {symbols}\n")
    found = []
    for i, s in enumerate(symbols, 1):
        print(f"[{i}/{len(symbols)}] Probing {s} ...")
        try:
            ok = probe_symbol_for_orders(API_KEY, SECRET_KEY, PASSPHRASE, s, probes_cap=probes_cap)
            print(f"  -> result: {ok}\n")
            if ok:
                found.append(s)
        except Exception as e:
            print(f"  probe error for {s}: {e}\n")
        time.sleep(0.8)

    print("Probe sweep finished. Symbols with detected orders:", found)
