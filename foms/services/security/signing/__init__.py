"""SESSION-SIGNING-STATE-00 signing tooling (additive expand).

Pure key-format decode/key-ID helpers and the state-machine prepare operations
(EMPTY→READY 등 deadline-null 준비). Runtime 서명 provider/serializer 전환·activation 은
SESSION-SIGNING-SECRET-01 몫이며 이 패키지는 그 어떤 runtime 서명 경로도 건드리지 않는다.
"""
