import pandas as pd
from config.settings import settings


class StockUniverse:
    def __init__(self):
        self.df = pd.read_csv(settings.NSE500_CSV)
        # Standardize column names
        self.df.columns = [c.strip() for c in self.df.columns]
        # Ensure we have required columns
        col_map = {}
        for col in self.df.columns:
            lower = col.lower()
            if "symbol" in lower:
                col_map[col] = "Symbol"
            elif "company" in lower:
                col_map[col] = "Company Name"
            elif "industry" in lower:
                col_map[col] = "Industry"
            elif "sector" in lower:
                col_map[col] = "Sector"
        if col_map:
            self.df = self.df.rename(columns=col_map)

    def get_all_symbols(self) -> list[str]:
        return self.df["Symbol"].tolist()

    def get_by_sector(self, sector: str) -> list[dict]:
        filtered = self.df[self.df["Sector"] == sector]
        return filtered.to_dict("records")

    def get_formatted_list(self) -> str:
        """Format NSE 500 list grouped by sector/industry for LLM context."""
        output = []
        group_col = "Sector" if "Sector" in self.df.columns else "Industry"
        for group_name, group in self.df.groupby(group_col):
            output.append(f"\n--- {group_name} ---")
            for _, row in group.iterrows():
                company = row.get("Company Name", "")
                industry = row.get("Industry", "")
                output.append(f"  {row['Symbol']} | {company} | {industry}")
        return "\n".join(output)

    def lookup(self, symbol: str) -> dict | None:
        match = self.df[self.df["Symbol"] == symbol]
        if match.empty:
            return None
        return match.iloc[0].to_dict()

    def validate_symbols(self, symbols: list[str]) -> list[str]:
        """Return only symbols that exist in the NSE 500 universe."""
        valid = set(self.df["Symbol"].tolist())
        return [s for s in symbols if s in valid]
