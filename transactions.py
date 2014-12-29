"""This file explains how we tell if a transaction is valid or not, it explains
how we update the database when new transactions are added to the blockchain."""
#Whether you are a signer depends on:
#5000=long_time*2-medium_time
#500=medium_time/2
#K-5000: how much money you had at this point.
#K-5000, -4500: random numbers selected here
#K-2500, -1000: random numbers revealed in this range
#K: sign on this block and make deposit and give hash(secret)
#K+2500, +3500: get reward. slasher is no longer possible. reveals secret

import blockchain, custom, copy, tools, forth
E_check=tools.E_check
def sigs_match(Sigs, Pubs, msg):
    pubs=copy.deepcopy(Pubs)
    sigs=copy.deepcopy(Sigs)
    def match(sig, pubs, msg):
        for p in pubs:
            if tools.verify(msg, sig, p):
                return {'bool':True, 'pub':p}
        return {'bool':False}
    for sig in sigs:
        a=match(sig, pubs, msg)
        if not a['bool']:
            return False
        sigs.remove(sig)
        pubs.remove(a['pub'])
    return True
def signature_check(tx):#verify that a transaction has a valid ECDSA signature on it.
    tx_copy = copy.deepcopy(tx)
    tx_copy.pop('signatures')
    if len(tx['pubkeys']) == 0:
        tools.log('pubkey error')
        return False
    if len(tx['signatures']) > len(tx['pubkeys']):
        tools.log('sigs too long')
        return False
    msg = tools.det_hash(tx_copy)
    if not sigs_match(copy.deepcopy(tx['signatures']),
                      copy.deepcopy(tx['pubkeys']), msg):
        tools.log('sigs do not match')
        return False
    return True
def mint_verify(tx, txs, out, DB):
    length=tools.local_get('length')
    height=tools.local_get('height')
    custom.block_fee(int(tx['height'])-height)
    gap=int(tx['height'])-height
    for t in txs:
        if t['type']=='mint': 
            out[0]+='no mint repeats'
    if not tools.fee_check(tx, txs, DB):
        out[0]+='fee check error'
        return False
    if tx['on_block']!=length+1:
        out[0]+='on wrong block'
        return False
    if len(filter(lambda x: x['type']=='mint', txs))>0:
        out[0]+='too many mints'
        return False
    amount=tools.mint_cost(txs, gap)
    if tx['amount']!=amount:
        tools.log('have: ' +str(tx['amount']))
        tools.log('need: ' +str(amount))
        tools.log('that amount is too big')
        return False
    return True
def spend_verify(tx, txs, out, DB):
    txaddr=tools.addr(tx)
    '''
    h=tx['recent_hash']
    l=tools.local_get('length')
    r=range(l-10, l)
    r=filter(lambda l: l>0, r)
    recent_blocks=map(lambda x:tools.db_get(x), r)
    recent_hashes=map(lambda x: x['block_hash'], recent_blocks)
    if h not in recent_hashes:
        tools.log('recent hash error')
        return False
    recent_txs=[]
    def f(b, recent_txs=recent_txs):
        recent_txs=recent_txs+b['txs']
    map(f, recent_blocks)
    recent_txs=filter(lambda t: t['type']=='spend', recent_txs)
    recent_txs=filter(lambda t: t['recent_hash']==h, recent_txs)
    recent_txs=filter(lambda t: t['to']==tx['to'], recent_txs)
    recent_txs=filter(lambda t: t['amount']==tx['amount'], recent_txs)
    recent_txs=filter(lambda t: t['fee']==tx['fee'], recent_txs)
    recent_txs=filter(lambda t: tools.addr(t)==txaddr, recent_txs)
    if len(recent_txs)>0:
        out[0]+='no repeated spends'
        return False
    '''
    if not signature_check(tx):
        out[0]+='signature check'
        return False
    if len(tx['to'])<=30:
        out[0]+='that address is too short'
        out[0]+='tx: ' +str(tx)
        return False
    if not tools.fee_check(tx, txs, DB):
        out[0]+='fee check error'
        return False
    return True
def sign_verify(tx, txs, out, DB):#check the validity of a transaction of type sign.
    a=tools.addr(tx)
    B=tx['B']#verify a proof that addr(tx) actually owned that much money long*2-medium ago.
    M=custom.all_money
    address=tools.addr(tx)
    block=tools.db_get(tx['on_block'])
    num=max(0,tx['on_block']-(custom.long_time*2-custom.medium_time))
    election_block=tools.db_get(num)
    if not signature_check(tx):
        out[0]+='signature check'
        return False
    if 'root_hash' not in election_block:
        out[0]+='no root hash'
        return False
    v=tools.db_verify(election_block['root_hash'], address, tx['proof'])
    if v==False:
        tools.log('your address did not exist that long ago.')
        return False
    if v['amount']!=tx['B']:
        tools.log('that is not how much money you had that long ago')
        return False
    if 'secret_hash' not in tx:
        tools.log('need the hash of a secret')
        return False
    for t in txs:
        if tools.addr(t)==address and t['type']=='sign':
            #tools.log('can only have one sign tx per block')
            return False
    if len(tx['jackpots'])<1: 
        tools.log('insufficient jackpots')
        return False
    if not signature_check(tx):
        out[0]+='signature check'
        return False
    length=tools.local_get('length')
    if int(tx['on_block'])!=int(length+1):
        out[0]+='this tx is for the wrong block. have '+str(length+1) +' need: ' +str(tx['on_block'])
        return False
    if tx['on_block']>0:
        if not tx['prev']==tools.db_get(length)['block_hash']:
            tools.log('must give hash of previous block')
            return False
    ran=tools.det_random(tx['on_block'])
    for j in tx['jackpots']:
        if type(j)!=int or j not in range(200):
               tools.log('bad jackpot')
               return False
        if len(filter(lambda x: x==j, tx['jackpots']))!=1:
               tools.log('no repeated jackpots')
               return False
        if not tools.winner(B, M, ran, address, j):
            tools.log('that jackpot is not valid: '+str(j))
            return False
    if tx['amount']<custom.minimum_deposit:
        tools.log('you have to deposit more than that')
        return False
    return True
def slasher_verify(tx, txs, out, DB):
    address=tools.addr(tx)
    acc=tools.db_get(address)
    if acc['secrets'][str(tx['on_block'])]['slashed']:
        tools.log('Someone already slashed them, or they already took the reward.')
        return False
    if not sign_verify(tx['tx1'], [], [''], {}):
        tools.log('one was not a valid tx')
        return False
    if not sign_verify(tx['tx2'], [], [''], {}):
        tools.log('two was not a valid tx')
        return False
    tx1=copy.deepcopy(tx['tx1'])
    tx2=copy.deepcopy(tx['tx2'])
    tx1.pop('signatures')
    tx2.pop('signatures')
    tx1=unpackage(package(tx1))
    tx2=unpackage(package(tx2))
    msg1=tools.det_hash(tx1)
    msg2=tools.det_hash(tx2)
    if msg1==msg2:
        tools.log('this is the same tx twice...')
        return False
    if tx1['on_block']!=tx2['on_block']:
        tools.log('these are on different lengths')
        return False
    return True
def sign_transaction(length, address):
    if length<=0:
        return {'secret_hash':0}
    txs=tools.db_get(length)['txs']
    txs=filter(lambda t: t['type']=='sign', txs)
    txs=filter(lambda t: tools.addr(t)==address, txs)
    return(txs[0])
def reward_verify(tx, txs, out, DB):
    address=tools.addr(tx)
    acc=tools.db_get(address)
    relative_reward=tools.relative_reward(tx['on_block'], address)
    sign_tx=sign_transaction(tx['on_block'], address)
    length=tools.local_get('length')
    if len(sign_tx['jackpots'])!=tx['jackpots']:
        tools.log('wrong number of jackpots')
        return False
    if length-custom.long_time+custom.medium_time/2<tx['on_block']or length-custom.long_time-custom.medium_time/2>tx['on_block']:
        tools.log('you did not wait the correct amount of time')
        return False
    if acc['secrets'][str(tx['on_block'])]['slashed']:
        tools.log('you were slashed, or you already claimed your reward at this height')
        return False
    if tx['amount']!=relative_reward+sign_tx['amount']:
        tools.log('reward wrong size')
        return False
    if sign_tx['secret_hash']!=tools.det_hash(tx['reveal']):
        tools.log('entropy+salt does not match')
        return False
    if tx['reveal']['entropy'] not in [0,1]:
        tools.log('entropy must be either 0 or 1')
        return False
    return True
def make_contract_verify(tx, txs, out, DB):
    if tools.db_existence(tx['id']):
        tools.log('contract already exists')
        return False
    contract={'gas':int(tx['amount'])-custom.make_contract_fee, 'mem':tx['mem'], 'stack':[]}
    if contract['gas']<0:
        tools.log('insufficient gas')
        return False
    return True
def contract_do_verify(tx, txs, out, DB):
    contract=tools.db_get(tx['contract_id'])
    if 'mem' not in contract:
        tools.log('not a contract')
        return False
    contract['gas']=tx['amount']-custom.contract_do_fee
    new_contract=forth.forth(tx['code'], forth.ex_language, contract)
    tools.log('new contract: ' +str(new_contract))
    if type(new_contract)==list:
        tools.log('contract failed: '+str(new_contract))
        return False
    if new_contract==['not enough gas']:
        tools.log(new_contract[0])
        return False
    if contract['mem']!=tx['old_mem']:
        tools.log('contrac: ' +str(contract))
        tools.log('tx: ' +str(tx))
        tools.log('old mem does not match')
        return False
    tools.log('new contract: ' +str(new_contract))
    if new_contract['gas']<0:
        tools.log('insufficient gas')
        return False
    return True
tx_check = {'mint':mint_verify,
            'spend':spend_verify,
            'sign':sign_verify,
            'slasher':slasher_verify,
            'reward':reward_verify,
            'make_contract':make_contract_verify,
            'contract_do':contract_do_verify}
'''
1) give signer's deposit
*reward is proportional to deposit size.
2) sign
3) double-sign slash
4) claim reward
*reveal one bit of entropy
*vote on system constants?
'''
#------------------------------------------------------
adjust_int=tools.adjust_int
adjust_string=tools.adjust_string
adjust_dict=tools.adjust_dict
adjust_list=tools.adjust_list
symmetric_put=tools.symmetric_put
def mint(tx, DB, add_block):
    address = tools.addr(tx)
    adjust_int(['amount'], address, tx['amount'], DB, add_block)
def spend(tx, DB, add_block):
    address = tools.addr(tx)
    adjust_int(['amount'], address, -int(tx['amount']), DB, add_block)
    adjust_int(['amount'], tx['to'], tx['amount'], DB, add_block)
    #adjust_int(['amount'], address, -custom.fee, DB, add_block)
    adjust_int(['amount'], address, -int(tx['fee']), DB, add_block)
def sign(tx, DB, add_block):#should include hash(entroy_bit and salt)
    address = tools.addr(tx)
    adjust_int(['amount'], address, -int(tx['amount']), DB, add_block)
    adjust_dict(['secrets'], address, False, {str(tx['on_block']):{'slashed':False}}, DB, add_block)
def slasher(tx, DB, add_block):
    address = tools.addr(tx)
    adjust_string(['secrets', tx['on_block'], 'slashed'], tools.addr(tx['tx1']), False, True, DB, add_block)
    adjust_int(['amount'], address, tx['amount']/5, DB, add_block)
    #tx={'amount':10000, 'tx1': , 'tx2': , 'reward_address': }
    #record
def reward(tx, DB, add_block):
    address = tools.addr(tx)
    length=tools.db_get('length')
    adjust_string(['secrets', tx['on_block'], 'slashed'], address, False, True, DB, add_block)
    adjust_dict(['entropy'], address, False, {str(tx['on_block']):{'power':tx['jackpots'],'vote':tx['reveal']}}, DB, add_block)
    adjust_int(['amount'], address, tx['amount'], DB, add_block)#relative_reward(on_block)+signer_bond
def make_contract(tx, DB, add_block):
    address = tools.addr(tx)
    adjust_int(['amount'], address, -int(tx['amount']), DB, add_block)
    contract={'gas':int(tx['amount'])-custom.make_contract_fee, 'mem':tx['mem'], 'stack':[]}
    symmetric_put(tx['id'], contract, DB, add_block)
    #put the contract into the database.
def contract_do(tx, DB, add_block):
    address = tools.addr(tx)
    contract=tools.db_get(tx['contract_id'])
    contract['gas']=tx['amount']-custom.contract_do_fee
    new_contract=forth.forth(tx['code'], forth.ex_language, contract)
    tools.log('new contract: ' +str(new_contract))
    new_contract['stack']=[]
    adjust_int(['amount'], address, -int(tx['amount']), DB, add_block)
    adjust_string(['mem'], tx['contract_id'], contract, new_contract['mem'], DB, add_block)
#{'cost':50000, 'code':'dup * + get'}#cost can be negative.
update = {'mint':mint,
          'spend':spend,
          'sign':sign,
          'slasher':slasher,
          'reward':reward,
          'make_contract':make_contract,
          'contract_do':contract_do}

#contract looks like:
#{'mem':{'a':'this is a forth script', 'b':'so is this', 'balance':'54'}}

#forth: + - / * ** % put get runfunc stop n-dup n-swap n-roll hash int unicode

#contract_do example
#I can use everything from forth besides state manipulation, and I can use the functions defined in the contract.
