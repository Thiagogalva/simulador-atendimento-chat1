BASE_ATENDIMENTOS = [
    {
        "id": 0,
        "titulo": "Tarifa / estorno",
        "fluxo": [
            {
                "cliente": "Abri uma contestação sobre um valor cobrado na minha conta e ainda não tive retorno.",
                "resposta_esperada": "Entendo a sua situação. Vou te explicar como está o andamento da análise e o prazo previsto para retorno."
            },
            {
                "cliente": "No extrato ainda não aparece nada.",
                "resposta_esperada": "Nesse caso, a análise ainda pode estar dentro do prazo. Como a solicitação foi registrada recentemente, o retorno pode levar até cinco dias úteis."
            },
            {
                "cliente": "Foi cobrada uma tarifa de cesta de serviços e eu não fui informada sobre isso.",
                "resposta_esperada": "Entendo o seu questionamento. Essa cobrança pode estar vinculada a um pacote de serviços contratado na abertura da conta ou em momento anterior."
            },
            {
                "cliente": "Mas eu deveria saber disso, correto?",
                "resposta_esperada": "Sim, é importante que você tenha clareza sobre qualquer serviço vinculado à sua conta. Posso te orientar também sobre como verificar ou alterar essa configuração."
            },
            {
                "cliente": "Eu só quero o valor de volta.",
                "resposta_esperada": "Entendo. Como já existe uma solicitação de estorno aberta, o ideal agora é aguardar a conclusão da análise dentro do prazo informado."
            },
            {
                "cliente": "Obrigada.",
                "resposta_esperada": "De nada. Agradeço o seu contato. Se precisar de mais alguma informação, estou à disposição."
            }
        ]
    },
    {
        "id": 1,
        "titulo": "Pix com bloqueio cautelar",
        "fluxo": [
            {
                "cliente": "Preciso que esse bloqueio seja liberado. Estou no banco para sacar meu dinheiro e a transferência foi feita de uma conta minha.",
                "resposta_esperada": "Entendo a urgência da sua situação. Vou verificar as informações no sistema para te orientar da forma mais clara possível."
            },
            {
                "cliente": "A transferência veio da minha própria conta e o valor é meu.",
                "resposta_esperada": "Obrigada por explicar. Mesmo quando a transferência é de conta da mesma titularidade, o sistema pode aplicar bloqueio cautelar por segurança."
            },
            {
                "cliente": "Minha mãe tem cirurgia amanhã e eu preciso desse valor agora.",
                "resposta_esperada": "Lamento muito pelo transtorno e entendo a gravidade da situação. No momento, esse tipo de bloqueio depende da análise de segurança e pode levar até 72 horas."
            },
            {
                "cliente": "Então devolve o dinheiro para a conta de origem agora.",
                "resposta_esperada": "No momento, a liberação ou devolução do valor só ocorre após a conclusão da análise. Eu não consigo fazer essa liberação manualmente por aqui."
            },
            {
                "cliente": "Vocês estão me causando transtorno e eu preciso de uma solução.",
                "resposta_esperada": "Compreendo a sua insatisfação. Para verificar a possibilidade de continuidade e orientação mais detalhada, vou direcionar o seu caso para o time especializado."
            },
            {
                "cliente": "Obrigada.",
                "resposta_esperada": "Eu que agradeço. O especialista dará continuidade ao atendimento e seguirá com as orientações do seu caso."
            }
        ]
    },
    {
        "id": 2,
        "titulo": "Conta bloqueada / Pix indisponível",
        "fluxo": [
            {
                "cliente": "Não consigo fazer Pix. Está dando erro.",
                "resposta_esperada": "Entendi. Vou verificar o que está acontecendo na sua conta. Peço só um momento, por gentileza."
            },
            {
                "cliente": "Qual é o problema?",
                "resposta_esperada": "Identifiquei que existe um bloqueio na sua conta neste momento, e por isso algumas movimentações podem ficar indisponíveis."
            },
            {
                "cliente": "Qual o motivo desse bloqueio? Preciso ir até a agência?",
                "resposta_esperada": "No momento, o motivo detalhado não aparece para mim aqui no atendimento. Esse caso precisa ser encaminhado ao setor responsável para análise."
            },
            {
                "cliente": "Posso resolver isso em uma agência?",
                "resposta_esperada": "Nesse caso, a orientação é seguir com a solicitação pelo canal responsável, porque a agência pode não conseguir concluir esse tipo de tratativa diretamente."
            },
            {
                "cliente": "O que vocês precisam para abrir essa solicitação?",
                "resposta_esperada": "Para abrir a solicitação, preciso do seu telefone com DDD, e-mail e do melhor horário para contato."
            },
            {
                "cliente": "Tenho salário para receber nessa conta. Como faço agora?",
                "resposta_esperada": "Entendo sua preocupação. Como existe um bloqueio ativo, o ideal é aguardar o retorno do setor responsável, que poderá orientar os próximos passos com segurança."
            },
            {
                "cliente": "Ok, só isso.",
                "resposta_esperada": "Perfeito. A solicitação já foi registrada. Agradeço o seu contato e, se precisar, estamos à disposição."
            }
        ]
    }
]