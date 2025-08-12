db = db.getSiblingDB('crypto_tracker');

// Create a user for your application
db.createUser({
  user: 'crypto_user',
  pwd: 'crypto_password',
  roles: [
    {
      role: 'readWrite',
      db: 'crypto_tracker'
    }
  ]
});

// Create the smart_wallets collection
db.createCollection('smart_wallets');

// Add indexes for better performance
db.smart_wallets.createIndex({ "address": 1 }, { unique: true });
db.smart_wallets.createIndex({ "score": 1 });
db.smart_wallets.createIndex({ "network": 1 });
db.smart_wallets.createIndex({ "created_at": 1 });

// Function to load wallets from your specific format: "score address"
function loadWalletsFromData() {
    // Your wallet data in the format: score address
    const walletData = `
1   0x3c46F73958e50aC8bedbc6cBEdd7718b73c69298
1   0x3f135ba020d0ed288d8dd85cd3d600451b121013
1   0xfe0dd0E80997bce29Ee3D7A677c4C7a250d5b144
2   0xbe31a54c78f6e73819fff78072be1660485c8105
3   0xcf706F82cbCFBf2e9c49A90F11Cd2ec37F2a98FB  
4   0xCBfEFAAFaCf7822458250c19755401EDB1875710 
5   0x89188de1eae4bccf97973e05ded9949362e376c1 
7   0x13b9db79f2f3372225b62851514389452e1f8acb  
7   0x27285ad49eed961f056339952cf39bcfbbee5ab4
10  0xf58C18BD3CeB788544bBBf1DACbE8F0857Da568e
12  0xF865067A5B9672f11AF8514440D9111AfD05d040
12  0xE14767042159E5BD2bf16F81A0FE387ab153Fbb4
14  0xf58C18BD3CeB788544bBBf1DACbE8F0857Da568e
14  0x406cbfc2d391bed42078138165465128b4e0cb06
14  0xAe5905De19D8E65b45D8179F71C72AF8018721CD
15  0xd16CF6cC98e62786fB5a72B96D41Fd1798241772
17  0xd81651Dd40455DA3106b599d8C68D4178af0c7ed  
17  0xdf839f2d5bbde84d6534e828d2f9ad8923a2d0c5  
17  0x9cb7b6292d0a387812d153685a22a01b4ae31a7e
18  0x86ec7469c855e24f328e96199be57642f0e26cea
19  0xdaEE0f096143B7fA8135DD783A271A3b8d027d23  
20  0x6233b326e9c2e4e363cbe8cf763085a6cbc13210
25  0xfb7ce7b78cc7356664d42c43216ebb6c7e49b627
27  0xee650f5599bd48f27b29b254a4c45322a755c6b4
29  0xd16CF6cC98e62786fB5a72B96D41Fd1798241772
30  0x2386491b64A37DA61b94fe0139bcf829300C473D
31  0x961f6af1729f276c9a053016a2da2706a19b7c42
32  0x10Cc182E808F31234E54A0C9F7f7652801B8E91E
32  0xf58C18BD3CeB788544bBBf1DACbE8F0857Da568e
32  0x76b2a9c7440793a833ccb7e64013be373cbae777
33  0x9e5e999c4506ea58e433898a6e8f5251db5a33be  
33  0x36ccdef4decfa6ae89707b1737e8fc56d275414f
33  0xea7fe8b57f1eadf03b8cf2306119fee3afb1906f  
34  0x45fc328b7c31fcec3be7a322f8309a0e5f348a10
36  0x1bd99cb26f4dcc7d422ab8d89792e853755a49f5
40  0x3837dCc83fdfb8ecee7F019B7BE3B0A9C3fAd4ab
41  0xcbbfece866a198f01ebd93b4ebe2d674542bec7c    
43  0xaac84e8df34f86edeafe037826c0d4a833237013
45  0x6ba46db059ca4160043970c072b7e684fdf75253
47  0xd2d289f6546cae3b25dc2bb653ca9241818b15cb  
47  0x2fcc020f72e5d2edd2a24d04f3dc90d7fdfbd1dd  
47  0x2bdf1a698d39a4358e2c162deacc038fadb8a9d5
48  0x5ee3b4435d67b30977f82a8b62f3db2ea8c4f4ff  
50  0xd37f0df3ca8214ee8dc64c12f3e83e3dc6471bd8
51  0xe177360194f8309889cdf06cf20db2ebad851fcf 
51  0x34cbd30e16d54904e61870ae892a73753e8afc0d
52  0x2aB63f6068ACAAFdF1a6e0EE40abE64EFEC8Ce72  \
55  0xf37832b43ad81d74b266d6935f394ec8037ec254
58  0x823b6b8DA270906f0a231223e46Edb5BDeA3ff13   
60  0xc3d9ca74d559709743c0d0611b958a7c98509bc1 
61  0xa95fe941a56af50385b1b0d704e4b2c92d04ac77
66  0x9da8bfa73922ba179b7ce8dc9d5d1d4444e48878
68  0xbCaF56f8E798FD5c279cE508b323dC998FfCC215  
68  0x39db730fd12f3b8e37801129974210710ddfd47c  
68  0x942a2b46ee68cfbdd8936fed52127c03c1c4a5c6
70  0x00000B7A7A859F1b7aB55579fD4e7b0b22064F3d  
70  0xf10b998ed1829ff7234f9dd7e6f02037d55f0196
72  0xf405513e92ec79c223282e895b7f223b1527a8c5
73  0xad7e5a9976bd8ed6fab0a590c7a1311283f3885d
75  0xf48e94Ab3BF4CAB38Ad31F62b9fb23c30f55fd58 
75  0x98dc55004ea322c53900c3aca926a528db6c18e1 
75  0x5a2a784477a15878a97c13ac6eefafb640f262f6
77  0xC30CF256dFC731193A4fe2b02c89Bf1815ec70a5
78  0xbb5ab67ca1a9d47ad9af425d3ef5100f79832577  
80  0xbA55BDbF959DF826dA6c35487eB15FaD2164662d  
80  0x1d417efad14171cd4777a99463096d3b89f62345
80  0xef95b8fac9273526b987b04645745f2e0eb03ac8  
81  0xf4e3bdaa19ca455b190977a623db05ee31316b06  
81  0xfacc356a3e74a98b40b7a0daf3574eaeac3fd10e
82  0x9B91fF4C7c4984DBfA9299282Cd3af9C37cE1F73 
83  0xCD8bDED162B7F8BDcE0da82F133bD75bbeF76835  
84  0xb761b4a43878bc0703c0327d66491bc283840265  
85  0x73aa6bf7fecc75a399aa06be3055102f034f21ed  
86  0x25c256f6437de6e9ba2c0ded33b87d99bd9de8db
87  0xCf2b7c6Bc98bfE0D6138A25a3b6162B51F75e05d  
87  0x21efcf78d0423274d88541bae8ae1b12c850225c
87  0x3Ccc64EA0AbFB664cBe8d5C24cdB24416b278AB4 
88  0xfefea9427bef554cc572bc4e887a0b9642fd8f4e
90  0xc650d2b433e2353b40a4fe003604c2fa92a3f752 
93  0x498B7b7ddB5E057e5d055C4E59f839DBD6e26Ff4  
94  0x10d5ebc8cc1d4e526d8d42d40d1e4a0c335294ea
96  0x83b1385D8126ecF64BFb3B4254D67eb9dB753BcC
97  0x74900cde422586ebcfce794e8b7a3b5ffb96480f  
98  0xa9bf1cf0c92424fbbe7c1cf5f8a1e8c8ae52da6b
99  0x538527f3602acad78596f17b422fcf5613af1409
99  0x000461a73d3985eef4923655782aa5d0de75c111
99  0x9b49067240f1191834efc9a139dd0187d63923e5
99  0xd76ff76ac8019c99237bde08d7c39dab5481bed2
99  0x043526144c0d06d58db4d37920c38a5926273d2d
99  0xa251520154ca342f0b1d702bf5a56f78c982405b
99  0x5d802e2fe48392c104ce0401c7eca8a4456f1f16
99  0x51fee9bf45c5dab188b57048658696edab9d72cf
99  0xafca747b067c40ae0dda3f170ae971a2cbf4d05c
102 0xf5e792fa36d47d69ff92f90ecfe3ddede16c04f6  
102 0x373dfc63eb5f1c29861fc26f91854744b00e68d1
102 0x4648aA9796926dc2fFdf525638404eB3D88e153F  
108 0x1EA2A806f60d3aBD361B2E9ec992Ba7b85258343
108 0x3e1a893184ccd858c9a3cf654889d93c77c36b5c
115 0xa7b052963ac07f8712b28062a4a393f5b3676fab
119 0xe674C81bdf132CF6e46Be106c82B3AB7A4AfD483  
119 0x4d85e1a6d298f0924fd7870024f30c48f9511e10
120 0xdde05da1122494c9af1694b377adbb43b47582c9   
121 0x3d7849b4114c56d10ab22fad7cdb7acad40a6164
122 0xCF2c042302D18F51cA99383759758ef5b0b43146  
128 0xd16cf6cc98e62786fb5a72b96d41fd1798241772 
130 0x8cdf1b6cfb693db9e171a1b9dda88c257e68638c 
130 0x9ecad9d9d3ed0938cc3b84732d3ffa8ece3a87c8
132 0xBb00900B914C71D7CC0d6c8865359499B9d0b3B6
134 0x733246BCEE1d39f3Cae699a1f1cFfC97D67D2e57  
134 0xb9bd7a488dac274962403d110d472ea195545a62  
135 0x193e75b60a4ca8bc842dc28604afc6c41afe972a
138 0x2aB63f6068ACAAFdF1a6e0EE40abE64EFEC8Ce72
141 0x7371e3c0629d101CE092a4ac7DbB893e6010B887 
141 0x719137b0dce78b3f76534ee2d8b6ccc591b25551
142 0x2aB63f6068ACAAFdF1a6e0EE40abE64EFEC8Ce72  
144 0x65f084b6306cb71c5a35f7d6b596e104333f93e2
151 0x7D3b1D9d524E56B22ab440cCCa828e9e7194e571 
157 0x56d3bda3e1f4bc779e558960b29d37112d74cd39
161 0x3d0dcc80999441e173d55b11c0d2272656d13d1a  
161 0x0bb454c2d4e642a5c18f1b3db4d020ba202907df   
161 0x4ac4a33101abb2aa21167de2b881429b915818a3 
164 0xeb80fcecbd2278b9f4ad15d08700b25bc7b4c85a
169 0x9e5e999c4506EA58E433898A6E8f5251db5a33bE
171 0x9B228B4F71B3Bc7e4b478251f218060D7B70Dc25
171 0xea7fe8B57F1EADF03b8cF2306119fEe3aFb1906F  
173 0x13eefb9dbf0a4ccaa27236fbfee5e227203315c7
174 0x8d9004e297950CAC958729153fD7Bb707d691338
180 0x9e025686eeae41a171f45aeb1078c729dbd68d72
184 0xDdcC6aCbc9267d75F1d20fAf3925a42e7300B673
185 0xBab2F87bcC50B8ABc542ED3BF152043F74F6910D
185 0xAA61A58830996a2b54902bAC0913641ccD362828
191 0xfD7E55a555555C2f25053A38eC744De1afeA4fA4  
191 0x442c70ef6b1e715aa3f4b305983d159d415f4c49  
191 0xbafc4696a29ed4511b76d0e98d930378ed468c02 
192 0x8cf0ff1497fe65e823bd077af11ca458a1a2b151
193 0xc04aa49a24ca82ee5c048f275aee6e9f74bd141d  
194 0x7f0c78d9304cbb96ef1d197e9c1eaa5ca84bb7e2
198 0x11d67Fa925877813B744aBC0917900c2b1D6Eb81
198 0xDdcC6aCbc9267d75F1d20fAf3925a42e7300B673 
198 0x2099482afe99dea3a3731f49491173e4701bc560   
198 0x2dbfcbb0db05d2286e8c1b19138f0b436696a75e
199 0x10cc182e808f31234e54a0c9f7f7652801b8e91e
199 0xb70399fc376c1b3cf3493556d2f14942323ef44f
199 0xef44326887a8866f525ecad41af6d878ebb5bb2a
199 0xad89368009bdbab92d2a631d04de15ca8a3b2ea4
199 0xd4b4cab5cf150f46448a8b312cf4d96521953c5f
199 0x657143820ee59b5f0da0de12bd199674178777cd
199 0xa946c445bf7f1675309fcd3a968da4da4e3a107a
199 0x8d73a36d78e2ae4a437053c9ce3be70d483ab74d
199 0xab0054e6d91e5be4b69c11ff7ce77c4571ff7c7c
199 0x952580d41f10db41d97fcd6b1984bc2538eefc2c
201 0x57ea2bff145b8a5bd1507a7f58464d4f81f862ad
203 0x11d67Fa925877813B744aBC0917900c2b1D6Eb81  
206 0xfdc3d1f88805ccdc18340ab8a819d84e307bfad2
213 0x4605b10011b2f73f7b3b2e4f62cfed47ed31dab9  
217 0x8ec19f4c362409db6aa2bc6cd39293e4f817f25a
225 0xfdf5b811d14cc1b2275a2370bff2ada4e3b4bde6
227 0xbCaF56f8E798FD5c279cE508b323dC998FfCC215  
230 0x1e5c797a569276bda2ee21750186000e01d2bb5b
233 0x348978BE35450fC594e2EE2D324d725a091Ae806
236 0x1bFc74841Fe9EC54EE4013458c98F6907F17E31d
226 0xcB3B2dEC6844E614034A9EDd853E0D972a18dBEa
242 0xd43625D0299eD239EA1F27cC739656162A305056 
247 0x46459033061d58df4742a35f63e9ec6aff5acf7d  
247 0x370b2e0f833d69c581987467c581ea13bf7cde44  
247 0x7b57f3d0c21495b5a9ddba39d06a38eed4939582
248 0x31FE301604FD45605EDbd2A9656440C7a1BeF337  
254 0x8b73c11e053581620bf5d7826d0942c50cb7b9cf
255 0xf48e94Ab3BF4CAB38Ad31F62b9fb23c30f55fd58   
259 0x6fbb774bfd12c4ac28c3efdc705676d242e7dbcf   
259 0x79a2ac3e55250b65b9f95c908c4cb8ebc4f37b1e
261 0x6863e1091e73de0cd4546ef0d12183133cd252bd
265 0x07ad7597f62360d449bea18ee225af545563843e
271 0xcf495e2cc0b1a59ea07d71e322eced8c71bafa99
272 0x2a0751d0a09042a1aeaf497204c06ccef99c28d9 
272 0x7a9803f2450e948f63bba32834792ce7aab02515
283 0xB3b4c2126cDCe49ab6d778e9479F368e503c352a 
281 0x891a144965c72c50201bf06f851d3a25d1d07946 
282 0x6d9c63f6aeac10bfded221e3fa1f4d796739edfd
285 0xd4a2aee94345bfa6aa1bdd3b95e8dc9d14b2ea19  
285 0xb254086ff72c8b90d24b6fa50c21df3a819b38b3 
287 0x5ee01da29e9dea5f8bc9b4a2b983f5ea9d731d2d
294 0xb533c3dfb722b8f7422e78d2fe4163d74bd1ca15  
296 0x8df04d551e3f7f5b03a67de79184bb919a97bbde
298 0x433d26C2Ea9D6F3A8f9A26B52495d324ee6A6d5b  
299 0x098ce140dd8374c84fa56b5109f523911eddcf89
300 0xcd497ef4e605e11d66497268f1784def34699b2f
`.trim();

    const wallets = [];
    const lines = walletData.split('\n').filter(line => line.trim() && !line.startsWith('#'));
    const seenAddresses = new Set(); // Track duplicates
    
    print(`Processing ${lines.length} lines...`);
    
    lines.forEach((line, index) => {
        const trimmed = line.trim();
        if (!trimmed) return;
        
        // Split by whitespace and filter empty parts
        const parts = trimmed.split(/\s+/).filter(part => part.length > 0);
        
        if (parts.length >= 2) {
            const scoreStr = parts[0];
            const address = parts[1];
            
            // Validate score is a number
            const score = parseInt(scoreStr);
            if (isNaN(score)) {
                print(`Invalid score on line ${index + 1}: ${scoreStr}`);
                return;
            }
            
            // Validate Ethereum address format
            if (address.match(/^0x[a-fA-F0-9]{40}$/)) {
                const addressLower = address.toLowerCase();
                
                // Check for duplicates
                if (seenAddresses.has(addressLower)) {
                    print(`Duplicate address found: ${address} (keeping first occurrence)`);
                    return;
                }
                seenAddresses.add(addressLower);
                
                // Determine network based on patterns or score ranges
                // You can adjust this logic based on your data
                let network = 'ethereum'; // default
                
                // Example: if you know certain score ranges are for Base
                // if (score >= 100) {
                //     network = 'base';
                // }
                
                // Or if you have specific addresses you know are Base wallets
                const baseWallets = [
                    '0xcf706f82cbcfbf2e9c49a90f11cd2ec37f2a98fb',
                    '0xa946c445bf7f1675309fcd3a968da4da4e3a107a'
                ];
                if (baseWallets.includes(addressLower)) {
                    network = 'base';
                }
                
                wallets.push({
                    address: addressLower,
                    score: score,
                    network: network,
                    created_at: new Date(),
                    imported_at: new Date(),
                    source: 'file_import',
                    active: true,
                    original_line: index + 1
                });
            } else {
                print(`Invalid address format on line ${index + 1}: ${address}`);
            }
        } else {
            print(`Invalid format on line ${index + 1}: ${trimmed}`);
        }
    });

    if (wallets.length > 0) {
        print(`Inserting ${wallets.length} valid wallets...`);
        
        let inserted = 0;
        let failed = 0;
        
        // Insert wallets one by one to handle duplicates gracefully
        wallets.forEach((wallet, index) => {
            try {
                db.smart_wallets.insertOne(wallet);
                inserted++;
                
                // Progress indicator
                if ((index + 1) % 10 === 0 || index === wallets.length - 1) {
                    print(`Inserted ${index + 1}/${wallets.length} wallets...`);
                }
            } catch (e) {
                failed++;
                if (e.code === 11000) {
                    print(`Duplicate wallet skipped: ${wallet.address}`);
                } else {
                    print(`Error inserting wallet ${wallet.address}: ${e.message}`);
                }
            }
        });
        
        print(`Import completed: ${inserted} inserted, ${failed} failed`);
    } else {
        print('No valid wallets found in data');
    }
}

// Load the wallets
print('Starting wallet import...');
loadWalletsFromData();

// Print detailed summary
const totalWallets = db.smart_wallets.countDocuments();
const ethWallets = db.smart_wallets.countDocuments({ network: 'ethereum' });
const baseWallets = db.smart_wallets.countDocuments({ network: 'base' });

// Score distribution
const scoreStats = db.smart_wallets.aggregate([
    {
        $group: {
            _id: null,
            minScore: { $min: "$score" },
            maxScore: { $max: "$score" },
            avgScore: { $avg: "$score" }
        }
    }
]).toArray()[0];

print('=== Database Initialization Summary ===');
print(`Total wallets imported: ${totalWallets}`);
print(`Ethereum wallets: ${ethWallets}`);
print(`Base wallets: ${baseWallets}`);
print(`Score range: ${scoreStats.minScore} - ${scoreStats.maxScore}`);
print(`Average score: ${scoreStats.avgScore.toFixed(2)}`);
print('Indexes created: address (unique), score, network, created_at');
print('Database user created: crypto_user');
print('Ready for crypto tracking! 🚀');