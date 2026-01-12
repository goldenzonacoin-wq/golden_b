from django.core.management.base import BaseCommand
from web3 import Web3
from django.conf import settings

class Command(BaseCommand):
    help = 'Check nonce and recent transactions for KMS address'

    def handle(self, *args, **options):
        w3 = Web3(Web3.HTTPProvider(settings.ETHEREUM_RPC_URL))
        address = "0xBfb33b5CC42C20De1dfc11CfdDa89C1CAd393e79"
        
        self.stdout.write("=" * 80)
        self.stdout.write(f"NONCE & TRANSACTION CHECK FOR {address}")
        self.stdout.write("=" * 80)
        
        # Check nonces
        latest_nonce = w3.eth.get_transaction_count(address, "latest")
        pending_nonce = w3.eth.get_transaction_count(address, "pending")
        
        self.stdout.write(f"\n📊 Nonce Status:")
        self.stdout.write(f"   Latest (confirmed): {latest_nonce}")
        self.stdout.write(f"   Pending (mempool):  {pending_nonce}")
        self.stdout.write(f"   Next to use:        {max(latest_nonce, pending_nonce)}")
        
        if pending_nonce > latest_nonce:
            self.stdout.write(self.style.WARNING(f"   ⚠️  {pending_nonce - latest_nonce} transaction(s) pending!"))
        
        # Check balance
        balance = w3.eth.get_balance(address)
        self.stdout.write(f"\n💰 POL Balance: {balance / 1e18:.4f}")
        
        # Try to get recent transactions from the latest blocks
        self.stdout.write(f"\n🔍 Checking last 50 blocks for transactions from this address...")
        
        latest_block = w3.eth.block_number
        found_txs = []
        
        for block_num in range(latest_block, max(0, latest_block - 50), -1):
            try:
                block = w3.eth.get_block(block_num, full_transactions=True)
                for tx in block.transactions:
                    if tx['from'].lower() == address.lower():
                        found_txs.append({
                            'hash': tx['hash'].hex(),
                            'nonce': tx['nonce'],
                            'block': block_num,
                            'to': tx.get('to', 'Contract Creation'),
                        })
            except:
                pass
        
        if found_txs:
            self.stdout.write(self.style.SUCCESS(f"\n✅ Found {len(found_txs)} recent transaction(s):"))
            for tx in sorted(found_txs, key=lambda x: x['nonce'], reverse=True):
                self.stdout.write(f"   Nonce {tx['nonce']}: {tx['hash'][:20]}... (block {tx['block']})")
                self.stdout.write(f"      → https://amoy.polygonscan.com/tx/{tx['hash']}")
        else:
            self.stdout.write(f"\n❌ No recent transactions found in last 50 blocks")
            self.stdout.write(f"   Check manually: https://amoy.polygonscan.com/address/{address}")
        
        # Recommendation
        self.stdout.write(f"\n" + "=" * 80)
        self.stdout.write(f"RECOMMENDATION:")
        self.stdout.write(f"=" * 80)
        
        if latest_nonce == 0 and pending_nonce == 0:
            self.stdout.write(self.style.SUCCESS(f"✅ No transactions yet. Use nonce 0."))
        elif pending_nonce > latest_nonce:
            self.stdout.write(self.style.WARNING(
                f"⚠️  Wait for pending transactions to confirm, then use nonce {pending_nonce}"
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"✅ Use nonce {latest_nonce} for next transaction"
            ))
        
        self.stdout.write(f"\n" + "=" * 80)