from web3 import Web3
from eth_account import Account
import json
import os
from decimal import Decimal
from django.conf import settings
from .models import SmartContractTransaction, VestingSchedule, CommitRevealTransfer, MiningReward, WhaleProtectionLimit, FeeExemption, BlacklistedAddress
import hashlib
import secrets


class SmartContractService:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(settings.ETHEREUM_RPC_URL))
        self.contract_address = settings.TOKEN_CONTRACT_ADDRESS
        
        # Load ABI
        abi_path = os.path.join(settings.BASE_DIR, 'redux', 'context', 'ATCToken.json')
        with open(abi_path, 'r') as f:
            contract_data = json.load(f)
            self.contract_abi = contract_data['abi']
        
        self.contract = self.w3.eth.contract(
            address=self.contract_address,
            abi=self.contract_abi
        )
        
        # Load admin private key for signing transactions
        # self.admin_account = Account.from_key(settings.ADMIN_PRIVATE_KEY)
    
    def get_token_info(self):
        """Get basic token information"""
        try:
            name = self.contract.functions.name().call()
            symbol = self.contract.functions.symbol().call()
            decimals = self.contract.functions.decimals().call()
            total_supply = self.contract.functions.totalSupply().call()
            cap = self.contract.functions.cap().call()
            
            return {
                'name': name,
                'symbol': symbol,
                'decimals': decimals,
                'total_supply': str(total_supply),
                'cap': str(cap)
            }
        except Exception as e:
            raise Exception(f"Failed to get token info: {str(e)}")
    
    def get_balance(self, address):
        """Get token balance for an address"""
        try:
            balance = self.contract.functions.balanceOf(address).call()
            return str(balance)
        except Exception as e:
            raise Exception(f"Failed to get balance: {str(e)}")
    
    def prepare_transfer_transaction(self, from_address, to_address, amount):
        """Prepare transfer transaction data for frontend signing"""
        try:
            amount_wei = int(Decimal(amount) * (10 ** 18))
            
            # Build transaction data
            transaction = self.contract.functions.transfer(
                to_address, 
                amount_wei
            ).build_transaction({
                'from': from_address,
                'gas': 100000,
                'gasPrice': self.w3.eth.gas_price,
                'nonce': self.w3.eth.get_transaction_count(from_address),
            })
            
            return {
                'transaction_data': transaction,
                'estimated_gas': transaction['gas'],
                'gas_price': str(transaction['gasPrice']),
                'nonce': transaction['nonce']
            }
            
        except Exception as e:
            raise Exception(f"Failed to prepare transfer: {str(e)}")
    
    def prepare_commit_transaction(self, from_address, to_address, amount, nonce=None):
        """Prepare commit transaction for private transfer"""
        try:
            if nonce is None:
                nonce = secrets.randbits(256)
            
            # Create commitment hash
            commitment_data = f"{to_address}{amount}{nonce}"
            commitment = Web3.keccak(text=commitment_data).hex()
            
            # Build commit transaction
            transaction = self.contract.functions.commitTransfer(
                commitment
            ).build_transaction({
                'from': from_address,
                'gas': 80000,
                'gasPrice': self.w3.eth.gas_price,
                'nonce': self.w3.eth.get_transaction_count(from_address),
            })
            
            return {
                'transaction_data': transaction,
                'commitment': commitment,
                'nonce': nonce,
                'estimated_gas': transaction['gas'],
                'gas_price': str(transaction['gasPrice'])
            }
            
        except Exception as e:
            raise Exception(f"Failed to prepare commit: {str(e)}")
    
    def prepare_reveal_transaction(self, from_address, to_address, amount, nonce):
        """Prepare reveal transaction for commit-reveal transfer"""
        try:
            amount_wei = int(Decimal(amount) * (10 ** 18))
            
            # Build reveal transaction
            transaction = self.contract.functions.revealTransfer(
                to_address,
                amount_wei,
                nonce
            ).build_transaction({
                'from': from_address,
                'gas': 120000,
                'gasPrice': self.w3.eth.gas_price,
                'nonce': self.w3.eth.get_transaction_count(from_address),
            })
            
            return {
                'transaction_data': transaction,
                'estimated_gas': transaction['gas'],
                'gas_price': str(transaction['gasPrice'])
            }
            
        except Exception as e:
            raise Exception(f"Failed to prepare reveal: {str(e)}")
    
    def reveal_transfer(self, from_user, commit_hash, to_address, amount, nonce):
        """Execute reveal transfer (second phase of commit-reveal)"""
        try:
            # Find the commit record
            commit_record = CommitRevealTransfer.objects.get(
                user=from_user,
                commit_hash=commit_hash,
                is_revealed=False
            )
            
            # Prepare reveal transaction
            reveal_data = self.prepare_reveal_transaction(
                from_user.wallet_address, to_address, amount, nonce
            )
            
            # Mark as revealed
            commit_record.is_revealed = True
            commit_record.save()
            
            return {
                'transaction_hash': 'prepared_for_signing',
                'message': 'Reveal transaction prepared'
            }
            
        except Exception as e:
            raise Exception(f"Reveal transfer failed: {str(e)}")
    
    def record_transaction(self, user, transaction_type, from_address, to_address, amount, tx_hash, **kwargs):
        """Record transaction after it's been signed and sent by frontend"""
        try:
            contract_tx = SmartContractTransaction.objects.create(
                user=user,
                transaction_type=transaction_type,
                from_address=from_address,
                to_address=to_address,
                amount=amount,
                transaction_hash=tx_hash,
                **kwargs
            )
            
            return contract_tx
            
        except Exception as e:
            raise Exception(f"Failed to record transaction: {str(e)}")
    
    def release_vested_tokens(self, schedule):
        """Release vested tokens for a schedule"""
        try:
            # Calculate releasable amount
            releasable = self.calculate_releasable_amount(schedule)
            
            if releasable <= 0:
                raise Exception("No tokens available for release")
            
            # Update schedule
            schedule.amount_released += releasable
            schedule.save()
            
            return {
                'released_amount': str(releasable),
                'transaction_hash': 'mock_tx_hash',
                'message': 'Tokens released successfully'
            }
            
        except Exception as e:
            raise Exception(f"Failed to release vested tokens: {str(e)}")
    
    def calculate_releasable_amount(self, schedule):
        """Calculate how many tokens can be released from vesting"""
        from django.utils import timezone
        
        now = timezone.now()
        if now < schedule.start_time:
            return Decimal('0')
        
        # Simple linear vesting calculation
        elapsed_months = (now - schedule.start_time).days / 30
        vesting_progress = min(elapsed_months / schedule.vesting_duration_months, 1.0)
        
        total_vested = schedule.total_amount * Decimal(str(vesting_progress))
        releasable = total_vested - schedule.amount_released
        
        return max(releasable, Decimal('0'))
    
    def claim_mining_reward(self, user, block_hash):
        """Claim mining reward for block validation"""
        try:
            # Check if reward already claimed
            existing_reward = MiningReward.objects.filter(
                miner=user,
                block_hash=block_hash
            ).first()
            
            if existing_reward:
                raise Exception("Reward already claimed for this block")
            
            # Create mining reward record
            reward_amount = Decimal('10.0')  # Fixed reward amount
            mining_reward = MiningReward.objects.create(
                miner=user,
                block_hash=block_hash,
                reward_amount=reward_amount
            )
            
            return {
                'reward_amount': str(reward_amount),
                'transaction_hash': 'mock_mining_tx_hash',
                'message': 'Mining reward claimed successfully'
            }
            
        except Exception as e:
            raise Exception(f"Failed to claim mining reward: {str(e)}")
    
    def mint_tokens(self, to_address, amount):
        """Admin: Mint new tokens"""
        try:
            return {
                'transaction_hash': 'mock_mint_tx_hash',
                'message': f'Minted {amount} tokens to {to_address}'
            }
        except Exception as e:
            raise Exception(f"Failed to mint tokens: {str(e)}")
    
    def burn_tokens(self, from_address, amount):
        """Admin: Burn tokens from address"""
        try:
            return {
                'transaction_hash': 'mock_burn_tx_hash',
                'message': f'Burned {amount} tokens from {from_address}'
            }
        except Exception as e:
            raise Exception(f"Failed to burn tokens: {str(e)}")
    
    def pause_contract(self):
        """Admin: Pause the contract"""
        try:
            return {
                'transaction_hash': 'mock_pause_tx_hash',
                'message': 'Contract paused successfully'
            }
        except Exception as e:
            raise Exception(f"Failed to pause contract: {str(e)}")
    
    def unpause_contract(self):
        """Admin: Unpause the contract"""
        try:
            return {
                'transaction_hash': 'mock_unpause_tx_hash',
                'message': 'Contract unpaused successfully'
            }
        except Exception as e:
            raise Exception(f"Failed to unpause contract: {str(e)}")
    
    def set_whale_protection_limit(self, limit_amount, time_period_hours):
        """Admin: Set whale protection limit"""
        try:
            whale_limit = WhaleProtectionLimit.objects.create(
                limit_amount=limit_amount,
                time_period_hours=time_period_hours
            )
            
            return {
                'transaction_hash': 'mock_whale_limit_tx_hash',
                'message': 'Whale protection limit set successfully'
            }
        except Exception as e:
            raise Exception(f"Failed to set whale protection limit: {str(e)}")
    
    def add_fee_exemption(self, address, reason=''):
        """Admin: Add fee exemption for address"""
        try:
            fee_exemption = FeeExemption.objects.create(
                address=address,
                reason=reason
            )
            
            return {
                'transaction_hash': 'mock_fee_exemption_tx_hash',
                'message': 'Fee exemption added successfully'
            }
        except Exception as e:
            raise Exception(f"Failed to add fee exemption: {str(e)}")
    
    def blacklist_address(self, address, reason=''):
        """Admin: Blacklist an address"""
        try:
            blacklisted = BlacklistedAddress.objects.create(
                address=address,
                reason=reason
            )
            
            return {
                'transaction_hash': 'mock_blacklist_tx_hash',
                'message': 'Address blacklisted successfully'
            }
        except Exception as e:
            raise Exception(f"Failed to blacklist address: {str(e)}")
    
    def unblacklist_address(self, address):
        """Admin: Remove address from blacklist"""
        try:
            BlacklistedAddress.objects.filter(
                address=address,
                is_active=True
            ).update(is_active=False)
            
            return {
                'transaction_hash': 'mock_unblacklist_tx_hash',
                'message': 'Address removed from blacklist successfully'
            }
        except Exception as e:
            raise Exception(f"Failed to unblacklist address: {str(e)}")
    
    def setup_vesting(self, user, beneficiary_address, amount, start_time, duration):
        """Setup vesting schedule for a user"""
        try:
            amount_wei = int(Decimal(amount) * (10 ** 18))
            start_timestamp = int(start_time.timestamp())
            
            # Build vesting transaction
            transaction = self.contract.functions.setupVesting(
                beneficiary_address,
                amount_wei,
                start_timestamp,
                duration
            ).build_transaction({
                'from': user.address,
                'gas': 150000,
                'gasPrice': self.w3.eth.gas_price,
                'nonce': self.w3.eth.get_transaction_count(user.address),
            })
            
            # Create vesting schedule record
            vesting = VestingSchedule.objects.create(
                user=user,
                beneficiary_address=beneficiary_address,
                total_amount=amount,
                start_time=start_time,
                duration=duration
            )
            
            SmartContractTransaction.objects.create(
                user=user,
                transaction_type='setup_vesting',
                to_address=beneficiary_address,
                amount=amount,
                transaction_hash=tx_hash.hex(),
                vesting_duration=duration
            )
            
            return {
                'transaction_data': transaction,
                'estimated_gas': transaction['gas'],
                'gas_price': str(transaction['gasPrice']),
                'nonce': transaction['nonce']
            }
            
        except Exception as e:
            raise Exception(f"Setup vesting failed: {str(e)}")
    
    def get_vesting_info(self, address):
        """Get vesting information for an address"""
        try:
            vesting_info = self.contract.functions.getVestingInfo(address).call()
            return {
                'total_amount': str(vesting_info[0]),
                'released_amount': str(vesting_info[1]),
                'vested_amount': str(vesting_info[2]),
                'remaining_amount': str(vesting_info[3])
            }
        except Exception as e:
            raise Exception(f"Failed to get vesting info: {str(e)}")
