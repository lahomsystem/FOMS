--
-- PostgreSQL database dump
--

-- Dumped from database version 16.8
-- Dumped by pg_dump version 16.8

-- Started on 2026-02-04 10:48:31

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- TOC entry 8 (class 2615 OID 82770)
-- Name: wdcalculator; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA wdcalculator;


ALTER SCHEMA wdcalculator OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 218 (class 1259 OID 25180)
-- Name: access_logs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.access_logs (
    id integer NOT NULL,
    user_id integer,
    action character varying NOT NULL,
    ip_address character varying,
    user_agent character varying,
    additional_data text,
    "timestamp" timestamp without time zone
);


ALTER TABLE public.access_logs OWNER TO postgres;

--
-- TOC entry 219 (class 1259 OID 25185)
-- Name: access_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.access_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.access_logs_id_seq OWNER TO postgres;

--
-- TOC entry 5072 (class 0 OID 0)
-- Dependencies: 219
-- Name: access_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.access_logs_id_seq OWNED BY public.access_logs.id;


--
-- TOC entry 220 (class 1259 OID 25186)
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


ALTER TABLE public.alembic_version OWNER TO postgres;

--
-- TOC entry 234 (class 1259 OID 82741)
-- Name: chat_attachments; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.chat_attachments (
    id integer NOT NULL,
    message_id integer NOT NULL,
    filename character varying(255) NOT NULL,
    file_type character varying(50) NOT NULL,
    file_size integer NOT NULL,
    storage_key character varying(500) NOT NULL,
    storage_url character varying(1000) NOT NULL,
    thumbnail_url character varying(1000),
    created_at timestamp without time zone NOT NULL
);


ALTER TABLE public.chat_attachments OWNER TO postgres;

--
-- TOC entry 233 (class 1259 OID 82740)
-- Name: chat_attachments_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.chat_attachments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.chat_attachments_id_seq OWNER TO postgres;

--
-- TOC entry 5073 (class 0 OID 0)
-- Dependencies: 233
-- Name: chat_attachments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.chat_attachments_id_seq OWNED BY public.chat_attachments.id;


--
-- TOC entry 232 (class 1259 OID 82720)
-- Name: chat_messages; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.chat_messages (
    id integer NOT NULL,
    room_id integer NOT NULL,
    user_id integer NOT NULL,
    message_type character varying(20) NOT NULL,
    content text,
    file_info jsonb,
    created_at timestamp without time zone NOT NULL
);


ALTER TABLE public.chat_messages OWNER TO postgres;

--
-- TOC entry 231 (class 1259 OID 82719)
-- Name: chat_messages_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.chat_messages_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.chat_messages_id_seq OWNER TO postgres;

--
-- TOC entry 5074 (class 0 OID 0)
-- Dependencies: 231
-- Name: chat_messages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.chat_messages_id_seq OWNED BY public.chat_messages.id;


--
-- TOC entry 230 (class 1259 OID 82703)
-- Name: chat_room_members; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.chat_room_members (
    id integer NOT NULL,
    room_id integer NOT NULL,
    user_id integer NOT NULL,
    joined_at timestamp without time zone NOT NULL,
    last_read_at timestamp without time zone
);


ALTER TABLE public.chat_room_members OWNER TO postgres;

--
-- TOC entry 229 (class 1259 OID 82702)
-- Name: chat_room_members_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.chat_room_members_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.chat_room_members_id_seq OWNER TO postgres;

--
-- TOC entry 5075 (class 0 OID 0)
-- Dependencies: 229
-- Name: chat_room_members_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.chat_room_members_id_seq OWNED BY public.chat_room_members.id;


--
-- TOC entry 228 (class 1259 OID 82684)
-- Name: chat_rooms; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.chat_rooms (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    order_id integer,
    created_by integer NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone
);


ALTER TABLE public.chat_rooms OWNER TO postgres;

--
-- TOC entry 227 (class 1259 OID 82683)
-- Name: chat_rooms_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.chat_rooms_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.chat_rooms_id_seq OWNER TO postgres;

--
-- TOC entry 5076 (class 0 OID 0)
-- Dependencies: 227
-- Name: chat_rooms_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.chat_rooms_id_seq OWNED BY public.chat_rooms.id;


--
-- TOC entry 243 (class 1259 OID 82815)
-- Name: order_attachments; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.order_attachments (
    id integer NOT NULL,
    order_id integer NOT NULL,
    filename character varying(255) NOT NULL,
    file_type character varying(50) NOT NULL,
    file_size integer NOT NULL,
    storage_key character varying(500) NOT NULL,
    thumbnail_key character varying(500),
    created_at timestamp without time zone NOT NULL
);


ALTER TABLE public.order_attachments OWNER TO postgres;

--
-- TOC entry 242 (class 1259 OID 82814)
-- Name: order_attachments_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.order_attachments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.order_attachments_id_seq OWNER TO postgres;

--
-- TOC entry 5077 (class 0 OID 0)
-- Dependencies: 242
-- Name: order_attachments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.order_attachments_id_seq OWNED BY public.order_attachments.id;


--
-- TOC entry 245 (class 1259 OID 82830)
-- Name: order_events; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.order_events (
    id integer NOT NULL,
    order_id integer NOT NULL,
    event_type character varying(50) NOT NULL,
    payload jsonb,
    created_by_user_id integer,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.order_events OWNER TO postgres;

--
-- TOC entry 244 (class 1259 OID 82829)
-- Name: order_events_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.order_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.order_events_id_seq OWNER TO postgres;

--
-- TOC entry 5078 (class 0 OID 0)
-- Dependencies: 244
-- Name: order_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.order_events_id_seq OWNED BY public.order_events.id;


--
-- TOC entry 247 (class 1259 OID 82853)
-- Name: order_tasks; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.order_tasks (
    id integer NOT NULL,
    order_id integer NOT NULL,
    title character varying(255) NOT NULL,
    status character varying(30) DEFAULT 'OPEN'::character varying NOT NULL,
    owner_team character varying(50),
    owner_user_id integer,
    due_date character varying,
    meta jsonb,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    task_type character varying(50) DEFAULT 'SLA_FOLLOWUP'::character varying NOT NULL,
    required boolean DEFAULT false NOT NULL,
    evidence_type character varying(50),
    template_key character varying(100),
    approver_user_id integer,
    approved_at timestamp without time zone,
    done_by_user_id integer,
    done_at timestamp without time zone
);


ALTER TABLE public.order_tasks OWNER TO postgres;

--
-- TOC entry 246 (class 1259 OID 82852)
-- Name: order_tasks_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.order_tasks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.order_tasks_id_seq OWNER TO postgres;

--
-- TOC entry 5079 (class 0 OID 0)
-- Dependencies: 246
-- Name: order_tasks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.order_tasks_id_seq OWNED BY public.order_tasks.id;


--
-- TOC entry 221 (class 1259 OID 25189)
-- Name: orders; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.orders (
    id integer NOT NULL,
    received_date character varying NOT NULL,
    received_time character varying,
    customer_name character varying NOT NULL,
    phone character varying NOT NULL,
    address text NOT NULL,
    product character varying NOT NULL,
    options text,
    notes text,
    status character varying,
    original_status character varying,
    deleted_at character varying,
    created_at timestamp without time zone,
    measurement_date character varying,
    measurement_time character varying,
    completion_date character varying,
    manager_name character varying,
    payment_amount integer,
    scheduled_date character varying,
    as_received_date character varying,
    as_completed_date character varying,
    is_regional boolean DEFAULT false,
    regional_sales_order_upload boolean DEFAULT false,
    regional_blueprint_sent boolean DEFAULT false,
    regional_order_upload boolean DEFAULT false,
    measurement_completed boolean,
    construction_type character varying(50),
    regional_cargo_sent boolean DEFAULT false,
    regional_construction_info_sent boolean DEFAULT false,
    regional_memo text,
    shipping_scheduled_date character varying,
    is_self_measurement boolean,
    is_cabinet boolean DEFAULT false,
    cabinet_status character varying DEFAULT 'RECEIVED'::character varying,
    shipping_fee integer DEFAULT 0,
    blueprint_image_url text,
    raw_order_text text,
    structured_data jsonb,
    structured_schema_version integer DEFAULT 1 NOT NULL,
    structured_confidence character varying(20),
    structured_updated_at timestamp without time zone,
    is_erp_beta boolean DEFAULT false NOT NULL
);


ALTER TABLE public.orders OWNER TO postgres;

--
-- TOC entry 222 (class 1259 OID 25202)
-- Name: orders_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.orders_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.orders_id_seq OWNER TO postgres;

--
-- TOC entry 5080 (class 0 OID 0)
-- Dependencies: 222
-- Name: orders_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.orders_id_seq OWNED BY public.orders.id;


--
-- TOC entry 223 (class 1259 OID 25203)
-- Name: security_logs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.security_logs (
    i